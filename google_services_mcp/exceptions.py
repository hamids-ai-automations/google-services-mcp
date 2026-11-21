"""Typed error hierarchy.

Every failure that can reach an MCP client is expressed as a
:class:`GoogleServicesMCPError` subclass with a stable machine-readable ``code``.
Messages are always safe to return to a client: they never contain access
tokens, refresh tokens, client secrets or raw upstream payloads.
"""

from __future__ import annotations

from typing import Any


class GoogleServicesMCPError(Exception):
    """Base class for all gateway errors."""

    code: str = "INTERNAL_ERROR"
    retryable: bool = False

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if retryable is not None:
            self.retryable = retryable

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


class ConfigurationError(GoogleServicesMCPError):
    code = "CONFIGURATION_ERROR"


class AuthenticationError(GoogleServicesMCPError):
    code = "AUTHENTICATION_REQUIRED"


class InvalidTokenError(AuthenticationError):
    code = "INVALID_TOKEN"


class InsufficientScopesError(AuthenticationError):
    code = "INSUFFICIENT_SCOPES"


class PermissionDeniedError(GoogleServicesMCPError):
    code = "PERMISSION_DENIED"


class ToolDisabledError(PermissionDeniedError):
    code = "TOOL_DISABLED"


class ConfirmationRequiredError(GoogleServicesMCPError):
    code = "CONFIRMATION_REQUIRED"


class PolicyViolationError(GoogleServicesMCPError):
    code = "POLICY_VIOLATION"


class InvalidArgumentError(GoogleServicesMCPError):
    code = "INVALID_ARGUMENT"


class NotFoundError(GoogleServicesMCPError):
    code = "NOT_FOUND"


class ConflictError(GoogleServicesMCPError):
    code = "CONFLICT"


class SizeLimitExceededError(GoogleServicesMCPError):
    code = "SIZE_LIMIT_EXCEEDED"


class QuotaExceededError(GoogleServicesMCPError):
    code = "QUOTA_EXCEEDED"
    retryable = True


class RateLimitedError(GoogleServicesMCPError):
    code = "RATE_LIMITED"
    retryable = True


class UpstreamError(GoogleServicesMCPError):
    code = "UPSTREAM_ERROR"
    retryable = True


class UpstreamTimeoutError(GoogleServicesMCPError):
    code = "TIMEOUT"
    retryable = True


class UnsupportedOperationError(GoogleServicesMCPError):
    code = "UNSUPPORTED_OPERATION"


def map_upstream_error(exc: Exception) -> GoogleServicesMCPError:
    """Translate a googleapiclient / requests / httplib2 failure into our taxonomy."""
    status = getattr(getattr(exc, "resp", None), "status", None)
    reason = ""
    try:  # googleapiclient.errors.HttpError
        import json

        payload = json.loads(exc.content.decode("utf-8"))  # type: ignore[attr-defined]
        reason = str(payload.get("error", {}).get("message", ""))[:400]
    except Exception:  # noqa: BLE001 - best effort only
        reason = str(exc)[:400]

    if status == 401:
        return InvalidTokenError("Google rejected the access token. Re-run `google-services-mcp auth login`.")
    if status == 403 and ("insufficient" in reason.lower() or "scope" in reason.lower()):
        return InsufficientScopesError(
            "The connected account has not granted the OAuth scope required by this tool.",
            details={"reason": reason},
        )
    if status == 403 and ("rate" in reason.lower() or "quota" in reason.lower()):
        return QuotaExceededError("Google API quota exceeded for this project.", details={"reason": reason})
    if status == 403:
        return PermissionDeniedError(
            "The connected Google account is not allowed to perform this operation.",
            details={"reason": reason},
        )
    if status == 404:
        return NotFoundError("The requested Google resource does not exist or is not shared with this account.")
    if status == 429:
        return RateLimitedError("Google rate-limited the request.", details={"reason": reason})
    if status and 500 <= int(status) < 600:
        return UpstreamError("Google API returned a server error.", details={"reason": reason})
    if exc.__class__.__name__ in {"Timeout", "ReadTimeout", "ConnectTimeout", "TimeoutError"}:
        return UpstreamTimeoutError("The Google API call timed out.")
    if isinstance(exc, GoogleServicesMCPError):
        return exc
    return UpstreamError("Google API call failed.", details={"reason": reason or type(exc).__name__})
