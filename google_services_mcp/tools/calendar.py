"""Google Calendar tools (MCP surface)."""

from __future__ import annotations

from ..permissions import Operation, ToolSpec
from ..services.calendar import CalendarService
from .common import confirm_guard
from .registry import Runtime, ToolResult, tool

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _svc(runtime: Runtime) -> CalendarService:
    return CalendarService(runtime.client, runtime.settings)


SPEC_CALENDARS = ToolSpec(
    name="calendar_list_calendars",
    service="calendar",
    operation=Operation.READ,
    policy_key="read",
    description="List calendars visible to the connected account with access roles.",
    scopes=SCOPES,
)
SPEC_EVENTS = ToolSpec(
    name="calendar_list_events",
    service="calendar",
    operation=Operation.READ,
    policy_key="read",
    description="List events in a time window (RFC3339), optionally filtered by free-text query.",
    scopes=SCOPES,
)
SPEC_GET = ToolSpec(
    name="calendar_get_event",
    service="calendar",
    operation=Operation.READ,
    policy_key="read",
    description="Fetch a single calendar event by ID.",
    scopes=SCOPES,
)
SPEC_FREEBUSY = ToolSpec(
    name="calendar_check_availability",
    service="calendar",
    operation=Operation.READ,
    policy_key="read",
    description="Query free/busy blocks for one or more calendars in a time window.",
    scopes=SCOPES,
)
SPEC_CREATE = ToolSpec(
    name="calendar_create_event",
    service="calendar",
    operation=Operation.WRITE,
    policy_key="create",
    description="Create an event. Supports dry_run=true to preview the payload without writing.",
    scopes=SCOPES,
    idempotent=False,
)
SPEC_UPDATE = ToolSpec(
    name="calendar_update_event",
    service="calendar",
    operation=Operation.WRITE,
    policy_key="update",
    description="Patch fields on an existing event (summary, times, location, attendees).",
    scopes=SCOPES,
)
SPEC_DELETE = ToolSpec(
    name="calendar_delete_event",
    service="calendar",
    operation=Operation.DESTRUCTIVE,
    policy_key="delete",
    description="Delete a calendar event. Requires confirm=true.",
    scopes=SCOPES,
    destructive=True,
)


@tool(SPEC_CALENDARS)
def calendar_list_calendars(runtime: Runtime) -> ToolResult:
    """List calendars."""
    return runtime.run(SPEC_CALENDARS, lambda: _svc(runtime).list_calendars())


@tool(SPEC_EVENTS)
def calendar_list_events(
    runtime: Runtime,
    calendar_id: str = "primary",
    time_min: str | None = None,
    time_max: str | None = None,
    query: str | None = None,
    max_results: int = 25,
) -> ToolResult:
    """List events in a window."""
    return runtime.run(
        SPEC_EVENTS,
        lambda: _svc(runtime).list_events(
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            query=query,
            max_results=max_results,
        ),
    )


@tool(SPEC_GET)
def calendar_get_event(runtime: Runtime, event_id: str, calendar_id: str = "primary") -> ToolResult:
    """Get one event."""
    return runtime.run(SPEC_GET, lambda: _svc(runtime).get_event(event_id, calendar_id=calendar_id))


@tool(SPEC_FREEBUSY)
def calendar_check_availability(
    runtime: Runtime,
    time_min: str,
    time_max: str,
    calendar_ids: list[str] | None = None,
    time_zone: str = "UTC",
) -> ToolResult:
    """Check free/busy."""
    return runtime.run(
        SPEC_FREEBUSY,
        lambda: _svc(runtime).check_availability(
            time_min=time_min, time_max=time_max, calendar_ids=calendar_ids, time_zone=time_zone
        ),
    )


@tool(SPEC_CREATE)
def calendar_create_event(
    runtime: Runtime,
    summary: str,
    start: str,
    end: str,
    time_zone: str | None = None,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    calendar_id: str = "primary",
    send_updates: str = "none",
    dry_run: bool = True,
) -> ToolResult:
    """Create an event (defaults to a dry run)."""
    return runtime.run(
        SPEC_CREATE,
        lambda: _svc(runtime).create_event(
            summary=summary,
            start=start,
            end=end,
            time_zone=time_zone,
            description=description,
            location=location,
            attendees=attendees,
            calendar_id=calendar_id,
            send_updates=send_updates,
            dry_run=dry_run,
        ),
    )


@tool(SPEC_UPDATE)
def calendar_update_event(
    runtime: Runtime,
    event_id: str,
    calendar_id: str = "primary",
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    time_zone: str | None = None,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    send_updates: str = "none",
) -> ToolResult:
    """Update an event."""
    return runtime.run(
        SPEC_UPDATE,
        lambda: _svc(runtime).update_event(
            event_id,
            calendar_id=calendar_id,
            summary=summary,
            start=start,
            end=end,
            time_zone=time_zone,
            description=description,
            location=location,
            attendees=attendees,
            send_updates=send_updates,
        ),
    )


@tool(SPEC_DELETE)
def calendar_delete_event(
    runtime: Runtime,
    event_id: str,
    calendar_id: str = "primary",
    send_updates: str = "none",
    confirm: bool = False,
) -> ToolResult:
    """Delete an event (requires confirm=true)."""

    def action() -> dict:
        confirm_guard(runtime.settings, confirm, "calendar_delete_event")
        return _svc(runtime).delete_event(event_id, calendar_id=calendar_id, send_updates=send_updates)

    return runtime.run(SPEC_DELETE, action)
