"""Execution wrapper: policy denial, success path, truncation and audit."""

from __future__ import annotations

import json

from google_services_mcp.permissions import Operation, ToolSpec
from google_services_mcp.tools.registry import Runtime

READ_SPEC = ToolSpec(
    name="drive_read_file",
    service="drive",
    operation=Operation.READ,
    policy_key="read",
    description="read a file",
)
CREATE_SPEC = ToolSpec(
    name="drive_create_folder",
    service="drive",
    operation=Operation.WRITE,
    policy_key="create",
    description="create a folder",
)


def _runtime(settings, tmp_path) -> Runtime:
    settings.audit.path = str(tmp_path / "audit.jsonl")
    return Runtime(settings)


def test_read_only_denial_is_reported_and_audited(settings, tmp_path) -> None:
    runtime = _runtime(settings, tmp_path)
    result = runtime.run(CREATE_SPEC, lambda: {"should": "never run"})

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "TOOL_DISABLED"

    lines = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert lines, "denial must be audited"
    record = json.loads(lines[-1])
    assert record["outcome"] == "denied"
    assert record["tool"] == "drive_create_folder"


def test_success_returns_meta(settings, tmp_path) -> None:
    runtime = _runtime(settings, tmp_path)
    result = runtime.run(READ_SPEC, lambda: {"name": "report.docx"})

    assert result.ok is True
    assert result.data == {"name": "report.docx"}
    assert result.meta is not None
    assert result.meta.tool == "drive_read_file"
    assert result.meta.permission_mode == "read_only"
    assert result.meta.correlation_id


def test_large_payloads_are_truncated(settings, tmp_path) -> None:
    settings.limits.max_result_chars = 64
    runtime = _runtime(settings, tmp_path)
    result = runtime.run(READ_SPEC, lambda: {"text": "x" * 500})

    assert result.ok is True
    assert result.meta is not None
    assert result.meta.truncated is True


def test_unexpected_exception_becomes_internal_error(settings, tmp_path) -> None:
    runtime = _runtime(settings, tmp_path)

    def boom():
        raise RuntimeError("kaboom")

    result = runtime.run(READ_SPEC, boom)
    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "INTERNAL_ERROR"
    assert "kaboom" not in result.error.message


def test_rate_limiter_blocks_bursts(settings, tmp_path) -> None:
    settings.limits.requests_per_minute = 1
    runtime = _runtime(settings, tmp_path)

    first = runtime.run(READ_SPEC, lambda: {"ok": True})
    second = runtime.run(READ_SPEC, lambda: {"ok": True})

    assert first.ok is True
    assert second.ok is False
    assert second.error is not None
    assert second.error.code == "RATE_LIMITED"
