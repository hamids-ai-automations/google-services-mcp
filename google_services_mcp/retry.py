"""Retry with exponential backoff, jitter and Retry-After support."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any

from .exceptions import GoogleServicesMCPError, map_upstream_error
from .logging_setup import get_logger

logger = get_logger("retry")

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _status_of(exc: Exception) -> int | None:
    status = getattr(getattr(exc, "resp", None), "status", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _retry_after(exc: Exception) -> float | None:
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
        return None


def execute_with_retry(
    request: Any,
    *,
    max_retries: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
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
                    }
                },
            )
            attempt += 1
            if delay > 0:
                sleep(delay)
