"""In-process token-bucket rate limiting."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from .exceptions import RateLimitedError


class TokenBucket:
    """Classic token bucket with an injectable clock (for tests)."""

    def __init__(
        self,
        rate_per_minute: int,
        *,
        capacity: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be positive")
        self.rate_per_second = rate_per_minute / 60.0
        self.capacity = float(capacity if capacity is not None else max(1, rate_per_minute))
        self._tokens = self.capacity
        self._clock = clock
        self._last = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._last = now
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate_per_second)

    def try_acquire(self, tokens: float = 1.0) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def acquire(self, tokens: float = 1.0, *, tool: str = "") -> None:
        if not self.try_acquire(tokens):
            retry_after = max(1, int(round(tokens / self.rate_per_second)))
            raise RateLimitedError(
                "Local request budget exhausted; retry shortly.",
                details={"retry_after_seconds": retry_after, "tool": tool},
            )

    @property
    def available(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens
