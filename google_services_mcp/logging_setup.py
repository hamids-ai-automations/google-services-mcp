"""Structured logging with secret redaction."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

from .security import redact

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "context", None)
        if isinstance(extra, dict):
            payload.update(redact(extra))
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info).splitlines()[-1][:400]
        return json.dumps(payload, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%dT%H:%M:%S%z")


def configure_logging(level: str | None = None, *, json_logs: bool | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    resolved_level = (level or os.environ.get("GSMCP_LOG_LEVEL", "INFO")).upper()
    if json_logs is None:
        json_logs = os.environ.get("GSMCP_LOG_JSON", "0") in {"1", "true", "yes"}
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(JsonFormatter() if json_logs else TextFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, resolved_level, logging.INFO))
    # Google libraries are noisy at DEBUG and can echo request bodies.
    for noisy in ("googleapiclient", "google_auth_httplib2", "urllib3", "httpx"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"gsmcp.{name}")


def log_event(logger: logging.Logger, level: int, message: str, **context: Any) -> None:
    logger.log(level, message, extra={"context": redact(context)})
