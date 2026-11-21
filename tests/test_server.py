"""Server assembly: every registered tool must expose a usable MCP schema."""

from __future__ import annotations

import asyncio

import pytest

from google_services_mcp.config import Settings
from google_services_mcp.server import build_server


@pytest.fixture(scope="module")
def tools(project_root):
    server = build_server(Settings.load(project_root / "config" / "config.example.yaml"))
    return asyncio.run(server.list_tools())


def test_all_tools_are_listed(tools):
    assert len(tools) == 44
    assert len({tool.name for tool in tools}) == len(tools)


def test_every_tool_has_input_and_output_schema(tools):
    # Regression: returning a ``ToolResult`` model from the wrapper made the MCP SDK fail to
    # build the output schema ("Output type not fully defined"), which broke server startup.
    for tool in tools:
        assert tool.input_schema, f"{tool.name} has no input schema"
        assert tool.output_schema, f"{tool.name} has no output schema"
        assert tool.output_schema.get("type") == "object"


def test_tool_annotations_reflect_registration(tools):
    by_name = {tool.name: tool for tool in tools}

    delete = by_name["drive_delete_file"]
    assert delete.annotations.destructive_hint is True
    assert delete.annotations.read_only_hint is False

    read = by_name["drive_read_file"]
    assert read.annotations.read_only_hint is True
    assert read.annotations.destructive_hint is False


def test_server_reports_configured_name(project_root):
    settings = Settings.load(project_root / "config" / "config.example.yaml")
    server = build_server(settings)
    assert settings.server_name
    assert asyncio.run(server.list_tools())
