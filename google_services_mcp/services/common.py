"""Shared helpers for the Google service adapters."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..exceptions import InvalidArgumentError, SizeLimitExceededError


def compact(value: Any) -> Any:
    """Remove ``None`` values and empty containers from API payloads."""
    if isinstance(value, dict):
        result = {key: compact(val) for key, val in value.items()}
        return {key: val for key, val in result.items() if val not in (None, {}, [])}
    if isinstance(value, list):
        return [compact(item) for item in value]
    return value


def first(seq: Iterable[Any] | None, default: Any = None) -> Any:
    if not seq:
        return default
    for item in seq:
        return item
    return default


def ensure_size(payload: Any, max_bytes: int, *, what: str) -> Any:
    size = len(payload) if isinstance(payload, (bytes, bytearray)) else len(str(payload).encode("utf-8"))
    if size > max_bytes:
        raise SizeLimitExceededError(
            f"{what} is {size} bytes, above the {max_bytes} byte limit configured on this server.",
            details={"size_bytes": size, "limit_bytes": max_bytes},
        )
    return payload


def normalize_file(item: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Drive file resource into a compact, stable shape."""
    owners = [owner.get("emailAddress") for owner in item.get("owners", []) if owner.get("emailAddress")]
    return compact(
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "mime_type": item.get("mimeType"),
            "modified_time": item.get("modifiedTime"),
            "created_time": item.get("createdTime"),
            "size_bytes": int(item["size"]) if str(item.get("size", "")).isdigit() else None,
            "owners": owners,
            "parents": item.get("parents"),
            "web_view_link": item.get("webViewLink"),
            "trashed": item.get("trashed"),
            "shared": item.get("shared"),
            "description": item.get("description"),
            "icon_link": item.get("iconLink"),
        }
    )


def normalize_spreadsheet_sheets(sheets: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sheet in sheets or []:
        props = sheet.get("properties", {})
        grid = props.get("gridProperties", {})
        out.append(
            compact(
                {
                    "sheet_id": props.get("sheetId"),
                    "title": props.get("title"),
                    "index": props.get("index"),
                    "rows": grid.get("rowCount"),
                    "columns": grid.get("columnCount"),
                    "hidden": props.get("hidden"),
                }
            )
        )
    return out


def validate_values_matrix(
    values: list[list[Any]], field: str = "values", *, max_rows: int = 10_000
) -> list[list[str]]:
    if not isinstance(values, list) or not values:
        raise InvalidArgumentError(f"`{field}` must be a non-empty list of rows.")
    if len(values) > max_rows:
        raise InvalidArgumentError(f"`{field}` exceeds the {max_rows} row limit.")
    normalized: list[list[str]] = []
    width: int | None = None
    for index, row in enumerate(values):
        if not isinstance(row, list):
            raise InvalidArgumentError(f"`{field}[{index}]` must be a list of cell values.")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise InvalidArgumentError(f"`{field}[{index}]` has a different column count than the first row.")
        normalized.append(["" if cell is None else str(cell) for cell in row])
    return normalized
