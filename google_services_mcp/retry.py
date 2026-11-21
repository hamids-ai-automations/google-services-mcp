"""Retry with exponential backoff, jitter and Retry-After support."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from datetime import UTC
from email.utils import parsedate_to_datetime
from typing import Any

from .exceptions import GoogleServicesMCPError, map_upstream_error
from .logging_setup import get_logger

logger = get_logger("retry")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# A single honoured Retry-After must never stall an MCP tool call for minutes.
# Google occasionally answers a 429 with a multi-minute (or HTTP-date) hint.
RETRY_AFTER_CEILING = 120.0


def _retry_after(exc: Exception, *, now: float | None = None) -> float | None:
    """Return the honoured Retry-After delay in seconds.

    Both forms from :rfc:`9110` section 10.2.3 are supported: ``delay-seconds``
    and ``HTTP-date``. Unparseable values return ``None`` so the caller falls
    back to exponential backoff.
    """
    resp = getattr(exc, "resp", None)
    headers = getattr(resp, "headers", None)
    if headers is None:
        return None
    raw = None
    try:
        raw = headers.get("retry-after") or headers.get("Retry-After")
    except AttributeError:
        return None
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        pass
    # HTTP-date form: "Wed, 21 Oct 2015 07:28:00 GMT".
    try:
        when = parsedate_to_datetime(str(raw))
    except (TypeError, ValueError, IndexError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    reference = time.time() if now is None else now
    return max(0.0, when.timestamp() - reference)


def _status_of(exc: Exception) -> int | None:
    status = getattr(getattr(exc, "resp", None), "status", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def execute_with_retry(
    request: Any,
    *,
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    retry_after_ceiling: float = RETRY_AFTER_CEILING,
    idempotent: bool = True,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> Any:
    """Execute a googleapiclient request with bounded retries.

    Non-idempotent requests (Gmail send, event creation without a stable id) are
    never retried automatically - a duplicate side effect is worse than a failure.
    """
    generator = rng or random
    attempt = 0
    while True:
        try:
            return request.execute()
        except GoogleServicesMCPError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalised below
            mapped = map_upstream_error(exc)
            status = _status_of(exc)
            retryable = mapped.retryable and (status in RETRYABLE_STATUS or status is None)
            if not idempotent or not retryable or attempt >= max_retries:
                raise mapped from exc
            hinted = _retry_after(exc)
            clamped = False
            if hinted is not None and hinted > retry_after_ceiling:
                hinted = retry_after_ceiling
                clamped = True
            delay = (
                hinted
                if hinted is not None
                else min(max_delay, base_delay * (2**attempt) * generator.uniform(0.75, 1.25))
            )
            logger.warning(
                "retrying Google API call",
                extra={
                    "context": {
                        "attempt": attempt + 1,
                        "status": status,
                        "delay": round(delay, 3),
                        "code": mapped.code,
                        "retry_after_clamped": clamped,
                    }
                },
            )
            attempt += 1
            if delay > 0:
                sleep(delay)
