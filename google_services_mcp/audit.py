"""Append-only audit trail with rotation, retention and an in-memory tail."""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import AuditSettings
from .logging_setup import get_logger
from .security import redact

logger = get_logger("audit")


class AuditLogger:
    """Writes one JSON object per tool call. Never stores payload bodies or tokens."""

    def __init__(self, settings: AuditSettings, *, buffer_size: int = 500) -> None:
        self.settings = settings
        self.path: Path = settings.resolved_path()
        self._lock = threading.Lock()
        self._tail: deque[dict[str, Any]] = deque(maxlen=buffer_size)
        self._last_rotation_check = 0.0
        if settings.enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- write path ---------------------------------------------------------
    def record(
        self,
        *,
        tool: str,
        service: str,
        operation: str,
        outcome: str,
        duration_ms: float | None = None,
        error_code: str | None = None,
        correlation_id: str | None = None,
        detail: dict[str, Any] | None = None,
        actor: str = "mcp-client",
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "tool": tool,
            "service": service,
            "operation": operation,
            "outcome": outcome,
            "actor": actor,
        }
        if duration_ms is not None:
            event["duration_ms"] = round(duration_ms, 2)
        if error_code:
            event["error_code"] = error_code
        if correlation_id:
            event["correlation_id"] = correlation_id
        if detail:
            event["detail"] = redact(detail)
        self._tail.appendleft(event)
        if not self.settings.enabled:
            return event
        line = json.dumps(event, default=str, ensure_ascii=False)
        with self._lock:
            try:
                self._rotate_if_needed()
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            except OSError as exc:  # never break a tool call because of disk issues
                logger.warning("audit write failed: %s", exc)
        return event

    # -- read path ----------------------------------------------------------
    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, len(self._tail) or 1))
        return list(self._tail)[:safe_limit]

    def stats(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for event in self._tail:
            key = f"{event['outcome']}:{event['service']}"
            counts[key] = counts.get(key, 0) + 1
        return {
            "enabled": self.settings.enabled,
            "path": str(self.path),
            "buffered_events": len(self._tail),
            "counts": counts,
        }

    # -- maintenance --------------------------------------------------------
    def _rotate_if_needed(self) -> None:
        now = time.time()
        if now - self._last_rotation_check < 30:
            return
        self._last_rotation_check = now
        try:
            if not self.path.exists() or self.path.stat().st_size < self.settings.max_bytes:
                self._purge_expired()
                return
        except OSError:
            return
        for index in range(self.settings.backup_count, 0, -1):
            src = self.path.with_suffix(self.path.suffix + f".{index}")
            dst = self.path.with_suffix(self.path.suffix + f".{index + 1}")
            if src.exists():
                if index == self.settings.backup_count:
                    src.unlink(missing_ok=True)
                else:
                    os.replace(src, dst)
        os.replace(self.path, self.path.with_suffix(self.path.suffix + ".1"))
        logger.info("rotated audit log at %s", self.path)

    def _purge_expired(self) -> None:
        cutoff = time.time() - self.settings.retention_days * 86_400
        try:
            for candidate in self.path.parent.glob(self.path.name + "*"):
                if candidate.stat().st_mtime < cutoff:
                    candidate.unlink(missing_ok=True)
        except OSError:
            return
