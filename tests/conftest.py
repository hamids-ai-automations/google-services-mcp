"""Shared fixtures for the google-services-mcp test suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from google_services_mcp.config import Settings  # noqa: E402

EXAMPLE_CONFIG = ROOT / "config" / "config.example.yaml"


@pytest.fixture(scope="session")
def project_root() -> Path:
    return ROOT


@pytest.fixture()
def settings() -> Settings:
    """The shipped example configuration (read-only, conservative)."""
    return Settings.load(EXAMPLE_CONFIG)


@pytest.fixture()
def make_settings():
    """Build a :class:`Settings` from a sparse override dict merged onto the example config."""

    def _factory(**overrides) -> Settings:
        base = Settings.load(EXAMPLE_CONFIG).model_dump()
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                base[key] = {**base[key], **value}
            else:
                base[key] = value
        return Settings.model_validate(base)

    return _factory
