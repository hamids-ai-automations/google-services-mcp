"""Configuration parsing: defaults, nested blocks, flat service flags, env overrides."""

from __future__ import annotations

import pytest

from google_services_mcp.config import ConfigurationError, Settings

ENV_KEYS = ("GSMCP_PERMISSIONS_MODE", "GSMCP_AUDIT_ENABLED", "GSMCP_MAX_PAGE_SIZE", "GSMCP_ALLOW_EMAIL_SEND")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_example_config_is_locked_down(settings: Settings) -> None:
    assert settings.permissions.mode.value == "read_only"
    assert settings.permissions.allow_email_send is False
    assert settings.permissions.services["drive"].flags["read"] is True
    assert settings.permissions.services["drive"].flags["delete"] is False
    assert settings.permissions.services["gmail"].flags["send"] is False


def test_server_block_is_flattened() -> None:
    settings = Settings.model_validate({"server": {"name": "x", "version": "9.9.9", "instructions": "hi"}})
    assert settings.server_name == "x"
    assert settings.server_version == "9.9.9"
    assert settings.instructions == "hi"


def test_flat_service_flags_are_folded_into_flags() -> None:
    settings = Settings.model_validate(
        {"permissions": {"mode": "read_write", "services": {"drive": {"enabled": True, "read": True, "create": True}}}}
    )
    policy = settings.permissions.services["drive"]
    assert policy.flags["read"] is True
    assert policy.flags["create"] is True
    assert policy.flags["delete"] is False


def test_env_overrides_take_precedence(monkeypatch) -> None:
    monkeypatch.setenv("GSMCP_PERMISSIONS_MODE", "read_write")
    monkeypatch.setenv("GSMCP_AUDIT_ENABLED", "false")
    monkeypatch.setenv("GSMCP_MAX_PAGE_SIZE", "25")
    settings = Settings.load()
    assert settings.permissions.mode.value == "read_write"
    assert settings.audit.enabled is False
    assert settings.limits.max_page_size == 25


def test_allowed_tools_env_is_parsed(monkeypatch) -> None:
    monkeypatch.setenv("GSMCP_ALLOWED_TOOLS", "drive_read_file, drive_list_files")
    settings = Settings.load()
    assert settings.permissions.allowed_tools == ["drive_read_file", "drive_list_files"]


def test_defaults_are_usable_but_read_only(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GSMCP_CONFIG_FILE", str(tmp_path / "absent.yaml"))
    settings = Settings.load()

    assert set(settings.permissions.services) == {"drive", "gmail", "calendar", "docs", "sheets"}
    assert all(policy.allows("read") for policy in settings.permissions.services.values())
    assert not any(
        any(policy.allows(k) for k in policy.flags if k != "read") for policy in settings.permissions.services.values()
    )


def test_invalid_yaml_raises_configuration_error(tmp_path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("permissions: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        Settings.load(broken)


def test_describe_never_leaks_paths(settings: Settings) -> None:
    described = settings.describe()
    assert "secrets" not in str(described)
    assert described["server"] == settings.server_name
