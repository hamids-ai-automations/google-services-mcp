"""Tool registry, runtime container and the single execution wrapper.

Every tool call passes through :meth:`Runtime.run`, which applies (in order):
rate limit -> permission policy -> execution -> redaction/truncation -> audit.
Results are always a :class:`ToolResult`, so the MCP layer never sees an
unhandled exception.
"""

from __future__ import annotations

import functools
import inspect
import time
import uuid
from collections.abc import Callable
from typing import Any

from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from ..audit import AuditLogger
from ..client import GoogleApiClient
from ..config import Settings
from ..exceptions import GoogleServicesMCPError
from ..logging_setup import get_logger
from ..permissions import PermissionPolicy, ToolSpec
from ..ratelimit import TokenBucket
from ..security import truncate

logger = get_logger("tools")

ToolFunction = Callable[..., "ToolResult"]


class ToolError(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ToolMeta(BaseModel):
    tool: str
    service: str
    operation: str
    correlation_id: str
    duration_ms: float
    permission_mode: str
    truncated: bool = False


class ToolResult(BaseModel):
    ok: bool = True
    data: Any | None = None
    error: ToolError | None = None
    meta: ToolMeta | None = None


class Runtime:
    """Holds everything a tool needs, injected once at server build time."""

    def __init__(
        self,
        settings: Settings,
        *,
        policy: PermissionPolicy | None = None,
        audit: AuditLogger | None = None,
        client: GoogleApiClient | None = None,
        limiter: TokenBucket | None = None,
    ) -> None:
        self.settings = settings
        self.policy = policy or PermissionPolicy(settings)
        self.audit = audit or AuditLogger(settings.audit, buffer_size=settings.buffer.max_events)
        self.client = client or GoogleApiClient(settings, _default_tokens(settings))
        self.limiter = limiter or TokenBucket(settings.limits.requests_per_minute)

    # -- execution ----------------------------------------------------------
    def run(self, spec: ToolSpec, fn: Callable[[], Any]) -> ToolResult:
        started = time.perf_counter()
        correlation_id = uuid.uuid4().hex[:12]
        try:
            self.limiter.acquire(tool=spec.name)
            self.policy.require(spec)
            raw = fn()
            payload, truncated = self._finalise(raw)
            duration = (time.perf_counter() - started) * 1000
            self.audit.record(
                tool=spec.name,
                service=spec.service,
                operation=spec.operation.value,
                outcome="success",
                duration_ms=duration,
                correlation_id=correlation_id,
                detail=_audit_detail(spec, raw),
            )
            return ToolResult(
                ok=True,
                data=payload,
                meta=ToolMeta(
                    tool=spec.name,
                    service=spec.service,
                    operation=spec.operation.value,
                    correlation_id=correlation_id,
                    duration_ms=round(duration, 2),
                    permission_mode=self.settings.permissions.mode.value,
                    truncated=truncated,
                ),
            )
        except GoogleServicesMCPError as exc:
            duration = (time.perf_counter() - started) * 1000
            denied = exc.code in {"TOOL_DISABLED", "PERMISSION_DENIED"}
            self.audit.record(
                tool=spec.name,
                service=spec.service,
                operation=spec.operation.value,
                outcome="denied" if denied else "error",
                duration_ms=duration,
                error_code=exc.code,
                correlation_id=correlation_id,
            )
            logger.warning(
                "tool failed",
                extra={"context": {"tool": spec.name, "code": exc.code, "correlation_id": correlation_id}},
            )
            return ToolResult(
                ok=False,
                error=ToolError(**exc.to_payload()),
                meta=ToolMeta(
                    tool=spec.name,
                    service=spec.service,
                    operation=spec.operation.value,
                    correlation_id=correlation_id,
                    duration_ms=round(duration, 2),
                    permission_mode=self.settings.permissions.mode.value,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - never leak a traceback to the client
            duration = (time.perf_counter() - started) * 1000
            logger.exception("unexpected tool error", extra={"context": {"tool": spec.name}})
            self.audit.record(
                tool=spec.name,
                service=spec.service,
                operation=spec.operation.value,
                outcome="error",
                duration_ms=duration,
                error_code="INTERNAL_ERROR",
                correlation_id=correlation_id,
            )
            return ToolResult(
                ok=False,
                error=ToolError(
                    code="INTERNAL_ERROR",
                    message=f"Unexpected internal error while running `{spec.name}` ({type(exc).__name__}).",
                ),
                meta=ToolMeta(
                    tool=spec.name,
                    service=spec.service,
                    operation=spec.operation.value,
                    correlation_id=correlation_id,
                    duration_ms=round(duration, 2),
                    permission_mode=self.settings.permissions.mode.value,
                ),
            )

    def _finalise(self, raw: Any) -> tuple[Any, bool]:
        if isinstance(raw, BaseModel):
            raw = raw.model_dump()
        limit = self.settings.limits.max_result_chars
        before = _size(raw)
        payload = truncate(raw, max_chars=limit)
        return payload, _size(payload) < before or before > limit


def _size(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return sum(_size(key) + _size(val) for key, val in value.items())
    if isinstance(value, list):
        return sum(_size(item) for item in value)
    return len(str(value))


def _audit_detail(spec: ToolSpec, raw: Any) -> dict[str, Any]:
    detail: dict[str, Any] = {"policy_key": spec.policy_key}
    if isinstance(raw, dict):
        for key in ("file_id", "spreadsheet_id", "message_id", "event_id", "document_id", "result_count"):
            if key in raw:
                detail[key] = raw[key]
        if "dry_run" in raw:
            detail["dry_run"] = raw["dry_run"]
    return detail


def _default_tokens(settings: Settings):
    from ..oauth.token_manager import TokenManager

    return TokenManager(settings.oauth)


def tool(spec: ToolSpec) -> Callable[[ToolFunction], ToolFunction]:
    """Attach a :class:`ToolSpec` to a tool function."""

    def decorator(fn: ToolFunction) -> ToolFunction:
        fn._gsmcp_spec = spec
        return fn

    return decorator


def tools_in_module(module: Any) -> list[ToolFunction]:
    found: list[ToolFunction] = []
    for name in dir(module):
        obj = getattr(module, name)
        if callable(obj) and isinstance(getattr(obj, "_gsmcp_spec", None), ToolSpec):
            found.append(obj)
    return sorted(found, key=lambda fn: fn._gsmcp_spec.name)


def bind(fn: ToolFunction, runtime: Runtime) -> ToolFunction:
    """Bind ``runtime`` as the first positional argument while preserving the public signature.

    The MCP SDK derives the JSON schema from ``inspect.signature``; hiding the ``runtime``
    parameter keeps it out of the tool schema.
    """

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = fn(runtime, *args, **kwargs)
        # Serialise to plain JSON types so the MCP SDK can derive an output schema.
        return result.model_dump(mode="json")

    signature = inspect.signature(fn)
    parameters = list(signature.parameters.values())[1:]  # drop `runtime`
    wrapper.__signature__ = signature.replace(  # type: ignore[attr-defined]
        parameters=parameters,
        return_annotation=dict[str, Any],
    )
    wrapper.__annotations__ = {
        key: value for key, value in getattr(fn, "__annotations__", {}).items() if key != "runtime"
    }
    wrapper.__annotations__["return"] = dict[str, Any]
    wrapper.__doc__ = fn.__doc__
    return wrapper


def register_module(server: Any, module: Any, runtime: Runtime) -> list[str]:
    """Register every decorated tool in ``module`` with the MCP server."""
    registered: list[str] = []
    for fn in tools_in_module(module):
        spec: ToolSpec = fn._gsmcp_spec
        server.add_tool(
            bind(fn, runtime),
            name=spec.name,
            title=spec.name.replace("_", " "),
            description=spec.description,
            annotations=ToolAnnotations(
                title=spec.name.replace("_", " "),
                read_only_hint=spec.read_only,
                destructive_hint=spec.destructive,
                idempotent_hint=spec.idempotent,
                open_world_hint=spec.open_world,
            ),
        )
        registered.append(spec.name)
    return registered
