"""Input validation helpers.

Every MCP tool argument passes through one of these before it reaches a Google
API. Validation failures raise :class:`InvalidArgumentError`, which the tool
wrapper converts into a structured, non-fatal error result.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .exceptions import InvalidArgumentError

# Google Drive/Sheets/Docs IDs are URL-safe base64ish strings.
_RESOURCE_ID = re.compile(r"^[A-Za-z0-9_\-]{5,200}$")
_EMAIL = re.compile(r"^[^@\s,;<>]{1,64}@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_RANGE = re.compile(r"^[A-Za-z0-9_\- '!.]+$")
_CALENDAR_ID = re.compile(r"^[A-Za-z0-9._%+\-]{3,120}@[A-Za-z0-9.\-]+$")

MAX_TEXT_CHARS = 250_000


def require_text(value: Any, field: str, *, max_chars: int = MAX_TEXT_CHARS, allow_empty: bool = False) -> str:
    if value is None or not isinstance(value, str):
        raise InvalidArgumentError(f"`{field}` must be a string.")
    text = value.strip() if allow_empty else value
    if not allow_empty and not text.strip():
        raise InvalidArgumentError(f"`{field}` must not be empty.")
    if len(value) > max_chars:
        raise InvalidArgumentError(f"`{field}` exceeds the {max_chars} character limit.")
    return value


def require_query(value: str, field: str = "query", *, max_chars: int = 512) -> str:
    text = require_text(value, field, max_chars=max_chars)
    if "\n" in text or "\r" in text:
        raise InvalidArgumentError(f"`{field}` must be a single line.")
    return text


def require_resource_id(value: str, field: str) -> str:
    text = require_text(value, field, max_chars=200)
    if not _RESOURCE_ID.match(text):
        raise InvalidArgumentError(
            f"`{field}` is not a valid Google resource id (expected letters, digits, '-' or '_')."
        )
    return text


def require_email(value: str, field: str = "email") -> str:
    text = require_text(value, field, max_chars=254)
    if not _EMAIL.match(text):
        raise InvalidArgumentError(f"`{field}` must be a single valid email address.")
    return text


def require_email_list(values: list[str], field: str, *, max_items: int = 100) -> list[str]:
    if not isinstance(values, list):
        raise InvalidArgumentError(f"`{field}` must be a list of email addresses.")
    if len(values) > max_items:
        raise InvalidArgumentError(f"`{field}` accepts at most {max_items} addresses.")
    return [require_email(item, field) for item in values]


def require_range(value: str, field: str = "range") -> str:
    text = require_text(value, field, max_chars=255)
    if not _RANGE.match(text):
        raise InvalidArgumentError(f"`{field}` must be an A1 notation range such as 'Sheet1!A1:D10'.")
    return text


def require_calendar_id(value: str, field: str = "calendar_id") -> str:
    text = require_text(value, field, max_chars=120)
    if text == "primary" or _CALENDAR_ID.match(text):
        return text
    raise InvalidArgumentError(f"`{field}` must be 'primary' or a calendar email id.")


def require_int(value: Any, field: str, *, minimum: int, maximum: int, default: int | None = None) -> int:
    if value is None and default is not None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidArgumentError(f"`{field}` must be an integer.")
    if not minimum <= value <= maximum:
        raise InvalidArgumentError(f"`{field}` must be between {minimum} and {maximum}.")
    return value


def require_bool(value: Any, field: str, *, default: bool = False) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise InvalidArgumentError(f"`{field}` must be a boolean.")
    return value


def require_rfc3339(value: str, field: str) -> datetime:
    text = require_text(value, field, max_chars=64)
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise InvalidArgumentError(f"`{field}` must be an RFC 3339 timestamp, e.g. 2026-05-01T09:00:00+05:00.") from exc
    if parsed.tzinfo is None:
        raise InvalidArgumentError(f"`{field}` must include a timezone offset.")
    return parsed


def require_timezone(value: str, field: str = "time_zone") -> str:
    text = require_text(value, field, max_chars=64)
    try:
        ZoneInfo(text)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidArgumentError(f"`{field}` must be an IANA time zone such as 'Asia/Karachi'.") from exc
    return text


def require_duration(minutes: Any, field: str = "duration_minutes") -> timedelta:
    value = require_int(minutes, field, minimum=1, maximum=24 * 60)
    return timedelta(minutes=value)


def require_path_string(value: str, field: str = "destination_path") -> str:
    text = require_text(value, field, max_chars=1024)
    if ".." in text.replace("\\", "/").split("/"):
        raise InvalidArgumentError(f"`{field}` must not contain '..' path segments.")
    if text.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", text):
        raise InvalidArgumentError(f"`{field}` must be relative to the configured download directory.")
    return text


def require_range_pair(start: str, end: str) -> tuple[datetime, datetime]:
    first = require_rfc3339(start, "time_min")
    second = require_rfc3339(end, "time_max")
    if second <= first:
        raise InvalidArgumentError("`time_max` must be later than `time_min`.")
    return first, second
