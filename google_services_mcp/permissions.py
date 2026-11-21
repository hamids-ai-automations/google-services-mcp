"""Server-side permission policy.

The policy is enforced inside the tool wrapper, not in the prompt, so an agent
cannot talk its way past it. Three independent gates must all pass:

1. the service is enabled and the tool's policy key is allowed by the mode,
2. the tool is registered at all (unregistered tools are unreachable), and
3. for the Gmail send path, the explicit ``allow_email_send`` guard is on.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from pydantic import BaseModel, Field

from .config import AccessMode, Settings
from .exceptions import ToolDisabledError


class Operation(str, Enum):  # noqa: UP042 - str+Enum keeps 3.11 loader compatibility
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class ToolSpec(BaseModel):
    """Static metadata attached to every tool function."""

    name: str
    service: str
    operation: Operation
    policy_key: str
    description: str
    scopes: list[str] = Field(default_factory=list)
    destructive: bool = False
    idempotent: bool = True
    open_world: bool = True

    @property
    def read_only(self) -> bool:
        return self.operation is Operation.READ


class PermissionPolicy:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.permissions.mode

    def check(self, spec: ToolSpec) -> tuple[bool, str]:
        """Return ``(allowed, reason)`` without raising."""
        if self.mode is AccessMode.READ_ONLY and spec.operation is not Operation.READ:
            return False, "Server is in read_only mode; write/destructive tools are disabled."
        if self.mode is AccessMode.RESTRICTED and spec.name not in self.settings.permissions.allowed_tools:
            return False, f"Tool `{spec.name}` is not in the restricted allow-list."
        service_policy = self.settings.permissions.service(spec.service)
        if not service_policy.enabled:
            return False, f"Service `{spec.service}` is disabled by policy."
        if not service_policy.allows(spec.policy_key):
            return False, (f"Policy key `{spec.service}.{spec.policy_key}` is not enabled (mode={self.mode.value}).")
        if spec.name.startswith("gmail_send") and not self.settings.permissions.allow_email_send:
            return False, "Outbound email is disabled (permissions.allow_email_send=false)."
        return True, "allowed"

    def require(self, spec: ToolSpec) -> None:
        allowed, reason = self.check(spec)
        if not allowed:
            raise ToolDisabledError(reason, details={"tool": spec.name, "mode": self.mode.value})

    def allowed_names(self, specs: Iterable[ToolSpec]) -> list[str]:
        return [spec.name for spec in specs if self.check(spec)[0]]

    def summary(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "allow_email_send": self.settings.permissions.allow_email_send,
            "restricted_allow_list": list(self.settings.permissions.allowed_tools),
            "services": {
                name: {"enabled": policy.enabled, **policy.flags}
                for name, policy in self.settings.permissions.services.items()
            },
        }


def is_destructive_guard_enabled(settings: Settings) -> bool:
    return settings.safety.require_confirmation_for_destructive
