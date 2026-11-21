"""Google Calendar adapter (v3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ..client import GoogleApiClient
from ..config import Settings
from ..exceptions import InvalidArgumentError
from ..retry import execute_with_retry
from .common import compact

ISO_OFFSET_RE = ("+", "-", "Z")


class CalendarService:
    def __init__(self, client: GoogleApiClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    def _api(self) -> Any:
        return self.client.calendar(["https://www.googleapis.com/auth/calendar.readonly"])

    def _execute(self, request: Any, *, idempotent: bool = True) -> Any:
        return execute_with_retry(
            request,
            max_retries=self.settings.google.max_retries,
            base_delay=self.settings.google.backoff_base_seconds,
            max_delay=self.settings.google.backoff_max_seconds,
            idempotent=idempotent,
        )

    # -- read ---------------------------------------------------------------
    def list_calendars(self) -> dict[str, Any]:
        api = self._api()
        data = self._execute(
            api.calendarList().list(maxResults=100, fields="items(id,summary,primary,timeZone,accessRole)")
        )
        return {
            "calendars": [
                compact(
                    {
                        "id": item.get("id"),
                        "summary": item.get("summary"),
                        "primary": item.get("primary"),
                        "time_zone": item.get("timeZone"),
                        "access_role": item.get("accessRole"),
                    }
                )
                for item in data.get("items", [])
            ]
        }

    def list_events(
        self,
        *,
        calendar_id: str = "primary",
        time_min: str | None = None,
        time_max: str | None = None,
        query: str | None = None,
        max_results: int = 25,
        single_events: bool = True,
        order_by: str = "startTime",
    ) -> dict[str, Any]:
        api = self._api()
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "calendarId": calendar_id,
            "timeMin": time_min or now.isoformat(),
            "timeMax": time_max,
            "q": query,
            "maxResults": min(max_results, self.settings.limits.max_page_size),
            "singleEvents": single_events,
            "orderBy": order_by if single_events else None,
        }
        data = self._execute(api.events().list(**compact(payload)))
        events = [_normalize_event(item) for item in data.get("items", [])]
        return {
            "events": events,
            "result_count": len(events),
            "next_page_token": data.get("nextPageToken"),
            "time_zone": data.get("timeZone"),
        }

    def get_event(self, event_id: str, *, calendar_id: str = "primary") -> dict[str, Any]:
        api = self._api()
        data = self._execute(api.events().get(calendarId=calendar_id, eventId=event_id))
        return {"event": _normalize_event(data)}

    def check_availability(
        self,
        *,
        time_min: str,
        time_max: str,
        calendar_ids: list[str] | None = None,
        time_zone: str = "UTC",
    ) -> dict[str, Any]:
        api = self._api()
        body = {
            "timeMin": time_min,
            "timeMax": time_max,
            "timeZone": time_zone,
            "items": [{"id": item} for item in (calendar_ids or ["primary"])],
        }
        data = self._execute(api.freebusy().query(body=body))
        return {"calendars": data.get("calendars", {}), "time_min": time_min, "time_max": time_max}

    # -- write --------------------------------------------------------------
    def create_event(
        self,
        *,
        summary: str,
        start: str,
        end: str,
        time_zone: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
        send_updates: str = "none",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        body = {
            "summary": summary,
            "start": _time_boundary(start, time_zone),
            "end": _time_boundary(end, time_zone),
            "description": description,
            "location": location,
            "attendees": [{"email": email} for email in attendees] if attendees else None,
        }
        body = compact(body)
        if dry_run:
            return {"created": False, "dry_run": True, "preview": body}
        _guard_time_order(body["start"], body["end"])
        api = self._api()
        data = self._execute(
            api.events().insert(calendarId=calendar_id, body=body, sendUpdates=send_updates),
            idempotent=False,
        )
        return {"created": True, "event": _normalize_event(data)}

    def update_event(
        self,
        event_id: str,
        *,
        calendar_id: str = "primary",
        summary: str | None = None,
        start: str | None = None,
        end: str | None = None,
        time_zone: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        send_updates: str = "none",
    ) -> dict[str, Any]:
        patch = compact(
            {
                "summary": summary,
                "start": _time_boundary(start, time_zone) if start else None,
                "end": _time_boundary(end, time_zone) if end else None,
                "description": description,
                "location": location,
                "attendees": [{"email": email} for email in attendees] if attendees is not None else None,
            }
        )
        if not patch:
            raise InvalidArgumentError("Provide at least one field to update.")
        if patch.get("start") and patch.get("end"):
            _guard_time_order(patch["start"], patch["end"])
        api = self._api()
        data = self._execute(
            api.events().patch(calendarId=calendar_id, eventId=event_id, body=patch, sendUpdates=send_updates),
            idempotent=True,
        )
        return {"updated": True, "event": _normalize_event(data)}

    def delete_event(
        self, event_id: str, *, calendar_id: str = "primary", send_updates: str = "none"
    ) -> dict[str, Any]:
        api = self._api()
        self._execute(
            api.events().delete(calendarId=calendar_id, eventId=event_id, sendUpdates=send_updates),
            idempotent=True,
        )
        return {"deleted": True, "event_id": event_id}


def _normalize_event(item: dict[str, Any]) -> dict[str, Any]:
    start = item.get("start", {})
    end = item.get("end", {})
    return compact(
        {
            "id": item.get("id"),
            "summary": item.get("summary"),
            "status": item.get("status"),
            "start": start.get("dateTime") or start.get("date"),
            "end": end.get("dateTime") or end.get("date"),
            "all_day": "date" in start,
            "time_zone": start.get("timeZone"),
            "location": item.get("location"),
            "description": (item.get("description") or "")[:800] or None,
            "attendees": [person.get("email") for person in item.get("attendees", []) if person.get("email")],
            "organizer": item.get("organizer", {}).get("email"),
            "html_link": item.get("htmlLink"),
            "hangout_link": item.get("hangoutLink"),
            "recurring": bool(item.get("recurringEventId")),
        }
    )


def _time_boundary(value: str, time_zone: str | None) -> dict[str, Any]:
    """Accept RFC3339 dateTime or an all-day ``YYYY-MM-DD`` date."""
    if not value:
        raise InvalidArgumentError("Time boundary must not be empty.")
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        datetime.strptime(value, "%Y-%m-%d")  # validate
        return {"date": value}
    has_offset = value.endswith("Z") or ("T" in value and ("+" in value[10:] or "-" in value[10:]))
    if not has_offset and not time_zone:
        raise InvalidArgumentError(
            f"`{value}` has no UTC offset; pass `time_zone` (e.g. 'Asia/Karachi') or an RFC3339 value ending in Z."
        )
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidArgumentError(f"Invalid RFC3339 timestamp: {value}") from exc
    payload = {"dateTime": value}
    if time_zone:
        payload["timeZone"] = time_zone
    return payload


def _guard_time_order(start: dict[str, Any], end: dict[str, Any]) -> None:
    def parse(boundary: dict[str, Any]) -> datetime:
        if "date" in boundary:
            return datetime.fromisoformat(boundary["date"]).replace(tzinfo=UTC)
        return datetime.fromisoformat(boundary["dateTime"].replace("Z", "+00:00"))

    if parse(end) <= parse(start):
        raise InvalidArgumentError("`end` must be later than `start`.")
    if parse(end) - parse(start) > timedelta(days=365):
        raise InvalidArgumentError("Event span exceeds 365 days; create a recurring event instead.")
