"""Retry policy tests: backoff, Retry-After handling (both RFC 9110 forms), idempotency."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from email.utils import format_datetime

import pytest

from google_services_mcp import retry as retry_mod
from google_services_mcp.exceptions import (
    GoogleServicesMCPError,
    NotFoundError,
    RateLimitedError,
    UpstreamError,
)
from google_services_mcp.retry import execute_with_retry


class _Resp:
    def __init__(self, status: int, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self.headers = headers or {}


class _Upstream(Exception):
    """Mimics googleapiclient.errors.HttpError closely enough for map_upstream_error."""

    def __init__(self, status: int, headers: dict[str, str] | None = None, message: str = "boom") -> None:
        super().__init__(message)
        self.resp = _Resp(status, headers)
        self.content = json.dumps({"error": {"message": message}}).encode("utf-8")


class _Request:
    """A request whose execute() replays a scripted list of outcomes."""

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def execute(self):
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _sleeps() -> tuple[list[float], object]:
    recorded: list[float] = []
    return recorded, recorded.append


def test_success_is_returned_without_sleeping():
    sleeps, sink = _sleeps()
    req = _Request(["ok"])
    assert execute_with_retry(req, sleep=sink) == "ok"
    assert req.calls == 1
    assert sleeps == []


def test_retryable_status_retries_then_succeeds_with_bounded_backoff():
    sleeps, sink = _sleeps()
    req = _Request([_Upstream(503), "ok"])
    result = execute_with_retry(req, base_delay=1.0, max_delay=8.0, sleep=sink, rng=random.Random(7))
    assert result == "ok"
    assert req.calls == 2
    assert len(sleeps) == 1
    # first attempt: base_delay * 2**0 * jitter(0.75..1.25)
    assert 0.75 <= sleeps[0] <= 1.25


def test_backoff_never_exceeds_max_delay():
    sleeps, sink = _sleeps()
    req = _Request([_Upstream(500)] * 6)
    with pytest.raises(UpstreamError):
        execute_with_retry(req, max_retries=5, base_delay=4.0, max_delay=8.0, sleep=sink, rng=random.Random(3))
    assert sleeps and all(d <= 8.0 for d in sleeps)


def test_retry_after_seconds_is_honoured_exactly():
    sleeps, sink = _sleeps()
    req = _Request([_Upstream(429, {"Retry-After": "7"}), "ok"])
    assert execute_with_retry(req, sleep=sink) == "ok"
    assert sleeps == [7.0]


def test_retry_after_accepts_lowercase_header_name():
    sleeps, sink = _sleeps()
    req = _Request([_Upstream(429, {"retry-after": "2"}), "ok"])
    assert execute_with_retry(req, sleep=sink) == "ok"
    assert sleeps == [2.0]


def test_retry_after_http_date_is_honoured(monkeypatch):
    """An HTTP-date hint used to be ignored, so the client re-hit a rate-limited API too early."""
    now = datetime(2026, 11, 21, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(retry_mod.time, "time", lambda: now.timestamp())
    stamp = format_datetime(datetime(2026, 11, 21, 12, 0, 30, tzinfo=UTC), usegmt=True)
    sleeps, sink = _sleeps()
    req = _Request([_Upstream(429, {"Retry-After": stamp}), "ok"])
    assert execute_with_retry(req, sleep=sink) == "ok"
    assert sleeps == [30.0]


def test_retry_after_in_the_past_does_not_sleep_negatively(monkeypatch):
    now = datetime(2026, 11, 21, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(retry_mod.time, "time", lambda: now.timestamp())
    stamp = format_datetime(datetime(2026, 11, 21, 11, 59, 0, tzinfo=UTC), usegmt=True)
    sleeps, sink = _sleeps()
    req = _Request([_Upstream(429, {"Retry-After": stamp}), "ok"])
    assert execute_with_retry(req, sleep=sink) == "ok"
    assert sleeps == []


def test_retry_after_is_clamped_to_ceiling():
    """A multi-minute hint must not stall an MCP tool call for minutes."""
    sleeps, sink = _sleeps()
    req = _Request([_Upstream(429, {"Retry-After": "600"}), "ok"])
    assert execute_with_retry(req, sleep=sink) == "ok"
    assert sleeps == [retry_mod.RETRY_AFTER_CEILING]


def test_retry_after_is_clamped_to_explicit_ceiling():
    sleeps, sink = _sleeps()
    req = _Request([_Upstream(429, {"Retry-After": "90"}), "ok"])
    execute_with_retry(req, retry_after_ceiling=10.0, sleep=sink)
    assert sleeps == [10.0]


def test_malformed_retry_after_falls_back_to_backoff():
    sleeps, sink = _sleeps()
    req = _Request([_Upstream(503, {"Retry-After": "soon"}), "ok"])
    execute_with_retry(req, base_delay=1.0, sleep=sink, rng=random.Random(11))
    assert len(sleeps) == 1
    assert 0.75 <= sleeps[0] <= 1.25


def test_non_idempotent_request_is_never_retried():
    sleeps, sink = _sleeps()
    req = _Request([_Upstream(503), "ok"])
    with pytest.raises(UpstreamError):
        execute_with_retry(req, idempotent=False, sleep=sink)
    assert req.calls == 1
    assert sleeps == []


def test_non_retryable_status_raises_immediately():
    sleeps, sink = _sleeps()
    req = _Request([_Upstream(404), "ok"])
    with pytest.raises(NotFoundError):
        execute_with_retry(req, sleep=sink)
    assert req.calls == 1
    assert sleeps == []


def test_retries_are_bounded_by_max_retries():
    sleeps, sink = _sleeps()
    req = _Request([_Upstream(429)])
    with pytest.raises(RateLimitedError):
        execute_with_retry(req, max_retries=2, retry_after_ceiling=0.0, sleep=sink)
    assert req.calls == 3  # initial attempt + 2 retries
    assert len(sleeps) == 2


def test_our_own_errors_pass_through_unmapped():
    original = GoogleServicesMCPError("already ours")
    req = _Request([original])
    with pytest.raises(GoogleServicesMCPError) as excinfo:
        execute_with_retry(req, sleep=lambda _d: None)
    assert excinfo.value is original


def test_unknown_exception_without_status_is_retried_then_wrapped():
    sleeps, sink = _sleeps()
    req = _Request([ValueError("socket closed"), "ok"])
    assert execute_with_retry(req, sleep=sink) == "ok"
    assert len(sleeps) == 1
