"""Permission gating: modes, per-service flags, restricted allow-lists."""

from __future__ import annotations

import pytest

from google_services_mcp.exceptions import ToolDisabledError
from google_services_mcp.permissions import Operation, PermissionPolicy, ToolSpec, is_destructive_guard_enabled


def spec(name: str, service: str, operation: Operation, policy_key: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        service=service,
        operation=operation,
        policy_key=policy_key,
        description=f"{name} test spec",
    )


READ = spec("drive_read_file", "drive", Operation.READ, "read")
CREATE = spec("drive_create_folder", "drive", Operation.WRITE, "create")
DELETE = spec("drive_delete_file", "drive", Operation.DESTRUCTIVE, "delete")
SEND = spec("gmail_send_email", "gmail", Operation.WRITE, "send")


def test_read_only_allows_reads_only(settings) -> None:
    policy = PermissionPolicy(settings)
    assert policy.check(READ) == (True, "allowed")
    allowed, reason = policy.check(CREATE)
    assert allowed is False
    assert "read_only" in reason


def test_require_raises_tool_disabled(settings) -> None:
    policy = PermissionPolicy(settings)
    with pytest.raises(ToolDisabledError):
        policy.require(CREATE)


def test_read_write_requires_flag(make_settings) -> None:
    enabled = make_settings(permissions={"mode": "read_write"}).permissions.model_dump()["services"]
    enabled["drive"] = {**enabled["drive"], "create": True}
    policy = PermissionPolicy(make_settings(permissions={"mode": "read_write", "services": enabled}))

    assert policy.check(CREATE)[0] is True
    allowed, reason = policy.check(DELETE)
    assert allowed is False
    assert "delete" in reason


def test_disabled_service_blocks_even_reads(make_settings) -> None:
    settings = make_settings(permissions={"mode": "read_write"})
    settings.permissions.services["drive"].enabled = False
    policy = PermissionPolicy(settings)
    allowed, reason = policy.check(READ)
    assert allowed is False
    assert "drive" in reason


def test_restricted_mode_honours_allow_list(make_settings) -> None:
    settings = make_settings(
        permissions={"mode": "restricted", "allowed_tools": ["drive_read_file"]},
    )
    policy = PermissionPolicy(settings)
    assert policy.check(READ)[0] is True
    allowed, reason = policy.check(CREATE)
    assert allowed is False
    assert "allow-list" in reason


def test_email_send_needs_both_switches(make_settings) -> None:
    services = make_settings().permissions.model_dump()["services"]
    services["gmail"] = {**services["gmail"], "send": False}
    policy = PermissionPolicy(make_settings(permissions={"mode": "read_write", "services": services}))
    assert policy.check(SEND)[0] is False

    services["gmail"] = {**services["gmail"], "send": True}
    settings = make_settings(permissions={"mode": "read_write", "allow_email_send": True, "services": services})
    assert PermissionPolicy(settings).check(SEND)[0] is True


def test_allowed_names_and_summary(settings) -> None:
    policy = PermissionPolicy(settings)
    names = policy.allowed_names([READ, CREATE, DELETE])
    assert names == ["drive_read_file"]
    summary = policy.summary()
    assert summary["mode"] == "read_only"
    assert "services" in summary


def test_destructive_guard_flag(settings) -> None:
    assert is_destructive_guard_enabled(settings) is True
    settings.safety.require_confirmation_for_destructive = False
    assert is_destructive_guard_enabled(settings) is False
