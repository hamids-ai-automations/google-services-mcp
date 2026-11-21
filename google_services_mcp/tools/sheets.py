"""Google Sheets tools (MCP surface)."""

from __future__ import annotations

from typing import Any

from ..permissions import Operation, ToolSpec
from ..services.sheets import SheetsService
from .common import confirm_guard
from .registry import Runtime, ToolResult, tool

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _svc(runtime: Runtime) -> SheetsService:
    return SheetsService(runtime.client, runtime.settings)


SPEC_INFO = ToolSpec(
    name="sheets_get_spreadsheet",
    service="sheets",
    operation=Operation.READ,
    policy_key="read",
    description="Get spreadsheet metadata: title, locale, time zone and the list of tabs.",
    scopes=SCOPES,
)
SPEC_READ = ToolSpec(
    name="sheets_read_range",
    service="sheets",
    operation=Operation.READ,
    policy_key="read",
    description="Read an A1 range (e.g. 'Sheet1!A1:D20') from a spreadsheet. Read-only.",
    scopes=SCOPES,
)
SPEC_BATCH_READ = ToolSpec(
    name="sheets_batch_read",
    service="sheets",
    operation=Operation.READ,
    policy_key="read",
    description="Read several A1 ranges from one spreadsheet in a single API call.",
    scopes=SCOPES,
)
SPEC_CREATE = ToolSpec(
    name="sheets_create_spreadsheet",
    service="sheets",
    operation=Operation.WRITE,
    policy_key="create",
    description="Create a new spreadsheet with an optional initial tab. Write operation.",
    scopes=SCOPES,
    idempotent=False,
)
SPEC_UPDATE = ToolSpec(
    name="sheets_update_range",
    service="sheets",
    operation=Operation.WRITE,
    policy_key="write",
    description="Overwrite an A1 range with a 2-D values array. Write operation; audited.",
    scopes=SCOPES,
)
SPEC_APPEND = ToolSpec(
    name="sheets_append_rows",
    service="sheets",
    operation=Operation.WRITE,
    policy_key="write",
    description="Append rows after the last row of a table. Write operation.",
    scopes=SCOPES,
    idempotent=False,
)
SPEC_CLEAR = ToolSpec(
    name="sheets_clear_range",
    service="sheets",
    operation=Operation.DESTRUCTIVE,
    policy_key="write",
    description="Clear values in an A1 range, keeping formatting. Destructive to cell data.",
    scopes=SCOPES,
    destructive=True,
)
SPEC_ADD_TAB = ToolSpec(
    name="sheets_add_sheet",
    service="sheets",
    operation=Operation.WRITE,
    policy_key="create",
    description="Add a new tab to an existing spreadsheet.",
    scopes=SCOPES,
    idempotent=False,
)
SPEC_DELETE_TAB = ToolSpec(
    name="sheets_delete_sheet",
    service="sheets",
    operation=Operation.DESTRUCTIVE,
    policy_key="delete",
    description="Delete a tab (by numeric sheetId) from a spreadsheet. Requires confirm=true.",
    scopes=SCOPES,
    destructive=True,
)


@tool(SPEC_INFO)
def sheets_get_spreadsheet(runtime: Runtime, spreadsheet_id: str) -> ToolResult:
    """Get spreadsheet metadata and tab list."""
    return runtime.run(SPEC_INFO, lambda: _svc(runtime).get_spreadsheet(spreadsheet_id))


@tool(SPEC_READ)
def sheets_read_range(
    runtime: Runtime,
    spreadsheet_id: str,
    range_a1: str,
    value_render: str = "FORMATTED_VALUE",
) -> ToolResult:
    """Read one A1 range."""
    return runtime.run(
        SPEC_READ,
        lambda: _svc(runtime).read_range(spreadsheet_id, range_a1, value_render=value_render),
    )


@tool(SPEC_BATCH_READ)
def sheets_batch_read(
    runtime: Runtime,
    spreadsheet_id: str,
    ranges: list[str],
    value_render: str = "FORMATTED_VALUE",
) -> ToolResult:
    """Read several A1 ranges at once."""
    return runtime.run(
        SPEC_BATCH_READ,
        lambda: _svc(runtime).batch_read(spreadsheet_id, ranges, value_render=value_render),
    )


@tool(SPEC_CREATE)
def sheets_create_spreadsheet(
    runtime: Runtime,
    title: str,
    sheet_title: str | None = None,
) -> ToolResult:
    """Create a spreadsheet."""
    return runtime.run(SPEC_CREATE, lambda: _svc(runtime).create_spreadsheet(title, sheet_title=sheet_title))


@tool(SPEC_UPDATE)
def sheets_update_range(
    runtime: Runtime,
    spreadsheet_id: str,
    range_a1: str,
    values: list[list[Any]],
    value_input: str = "USER_ENTERED",
) -> ToolResult:
    """Write a values matrix into an A1 range."""
    return runtime.run(
        SPEC_UPDATE,
        lambda: _svc(runtime).update_range(spreadsheet_id, range_a1, values, value_input=value_input),
    )


@tool(SPEC_APPEND)
def sheets_append_rows(
    runtime: Runtime,
    spreadsheet_id: str,
    range_a1: str,
    values: list[list[Any]],
    value_input: str = "USER_ENTERED",
) -> ToolResult:
    """Append rows to a table."""
    return runtime.run(
        SPEC_APPEND,
        lambda: _svc(runtime).append_rows(spreadsheet_id, range_a1, values, value_input=value_input),
    )


@tool(SPEC_CLEAR)
def sheets_clear_range(runtime: Runtime, spreadsheet_id: str, range_a1: str) -> ToolResult:
    """Clear an A1 range."""
    return runtime.run(SPEC_CLEAR, lambda: _svc(runtime).clear_range(spreadsheet_id, range_a1))


@tool(SPEC_ADD_TAB)
def sheets_add_sheet(runtime: Runtime, spreadsheet_id: str, sheet_title: str) -> ToolResult:
    """Add a tab."""
    return runtime.run(SPEC_ADD_TAB, lambda: _svc(runtime).add_sheet(spreadsheet_id, sheet_title))


@tool(SPEC_DELETE_TAB)
def sheets_delete_sheet(
    runtime: Runtime,
    spreadsheet_id: str,
    sheet_id: int,
    confirm: bool = False,
) -> ToolResult:
    """Delete a tab (requires confirm=true)."""

    def action() -> dict:
        confirm_guard(runtime.settings, confirm, "sheets_delete_sheet")
        return _svc(runtime).delete_sheet(spreadsheet_id, sheet_id)

    return runtime.run(SPEC_DELETE_TAB, action)
