"""Shared guard helpers for tool definitions."""

from __future__ import annotations

from ..config import Settings
from ..exceptions import ConfirmationRequiredError, InvalidArgumentError


def confirm_guard(settings: Settings, confirm: bool, action: str) -> None:
    """Block irreversible actions unless the caller passes ``confirm=true``."""
    if settings.safety.require_confirmation_for_destructive and not confirm:
        raise ConfirmationRequiredError(
            f"`{action}` is irreversible and requires an explicit confirm=true from the user.",
            details={"action": action, "why": "destructive operation"},
        )


def bounded_int(value: int, *, name: str, minimum: int, maximum: int) -> int:
    if value < minimum or value > maximum:
        raise InvalidArgumentError(f"`{name}` must be between {minimum} and {maximum}.")
    return value


def clean_query(settings: Settings, query: str, name: str = "query") -> str:
    query = query.strip()
    if not query:
        raise InvalidArgumentError(f"`{name}` must not be empty.")
    if len(query) > settings.limits.max_search_query_chars:
        raise InvalidArgumentError(
            f"`{name}` exceeds {settings.limits.max_search_query_chars} characters.",
            details={"length": len(query)},
        )
    return query
