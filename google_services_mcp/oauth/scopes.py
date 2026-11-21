"""OAuth scope catalog and least-privilege resolution."""

from __future__ import annotations

from ..exceptions import InsufficientScopesError

SCOPE_CATALOG: dict[str, str] = {
    # Drive
    "drive.readonly": "https://www.googleapis.com/auth/drive.readonly",
    "drive.file": "https://www.googleapis.com/auth/drive.file",
    "drive": "https://www.googleapis.com/auth/drive",
    # Sheets
    "spreadsheets.readonly": "https://www.googleapis.com/auth/spreadsheets.readonly",
    "spreadsheets": "https://www.googleapis.com/auth/spreadsheets",
    # Gmail
    "gmail.readonly": "https://www.googleapis.com/auth/gmail.readonly",
    "gmail.compose": "https://www.googleapis.com/auth/gmail.compose",
    "gmail.send": "https://www.googleapis.com/auth/gmail.send",
    "gmail.modify": "https://www.googleapis.com/auth/gmail.modify",
    # Calendar
    "calendar.readonly": "https://www.googleapis.com/auth/calendar.readonly",
    "calendar.events": "https://www.googleapis.com/auth/calendar.events",
    "calendar": "https://www.googleapis.com/auth/calendar",
    # Docs
    "documents.readonly": "https://www.googleapis.com/auth/documents.readonly",
    "documents": "https://www.googleapis.com/auth/documents",
    # Identity
    "userinfo.email": "https://www.googleapis.com/auth/userinfo.email",
    "openid": "openid",
}

# Coarse scope -> scopes that are broader but still satisfy it.
_WIDENING: dict[str, tuple[str, ...]] = {
    "drive.readonly": ("drive",),
    "spreadsheets.readonly": ("spreadsheets",),
    "gmail.readonly": ("gmail.modify",),
    "gmail.compose": ("gmail.modify",),
    "gmail.send": ("gmail.modify",),
    "calendar.readonly": ("calendar", "calendar.events"),
    "documents.readonly": ("documents",),
    "drive.file": ("drive",),
}


def resolve_scopes(keys: list[str]) -> list[str]:
    """Map short scope keys to full OAuth scope URLs, preserving order."""
    resolved: list[str] = []
    for key in keys:
        url = SCOPE_CATALOG.get(key, key)
        if url not in resolved:
            resolved.append(url)
    return resolved


def default_login_scopes(include_write: bool = False) -> list[str]:
    keys = [
        "openid",
        "userinfo.email",
        "drive.readonly",
        "spreadsheets.readonly",
        "gmail.readonly",
        "calendar.readonly",
        "documents.readonly",
    ]
    if include_write:
        keys += ["drive.file", "spreadsheets", "gmail.compose", "calendar.events", "documents"]
    return resolve_scopes(keys)


def satisfied_by(required_scope: str, granted: set[str]) -> bool:
    if required_scope in granted:
        return True
    return any(alias in granted for alias in _WIDENING.get(required_scope, ()))


def missing_scopes(required: list[str], granted: set[str]) -> list[str]:
    return [scope for scope in required if not satisfied_by(scope, granted)]


def require_scopes(required: list[str], granted: set[str]) -> None:
    missing = missing_scopes(required, granted)
    if missing:
        short = ", ".join(scope.rsplit("/", 1)[-1] for scope in missing)
        raise InsufficientScopesError(
            f"The connected account has not granted these OAuth scopes: {short}. "
            "Re-run `google-services-mcp auth login --write` to re-consent.",
            details={"missing_scopes": missing},
        )
