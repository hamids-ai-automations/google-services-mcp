"""Tool packages: one module per Google service, all registered through ``registry``."""

from __future__ import annotations

from typing import Any

from . import calendar, docs, drive, gmail, sheets
from .registry import Runtime, register_module, tools_in_module

MODULES = (drive, sheets, gmail, calendar, docs)


def register_all(server: Any, runtime: Runtime) -> list[str]:
    """Register every service module and return the registered tool names."""
    registered: list[str] = []
    for module in MODULES:
        registered.extend(register_module(server, module, runtime))
    return sorted(registered)


def all_specs():
    """Return every :class:`ToolSpec` known to the service modules (no server required)."""
    specs = []
    for module in MODULES:
        for fn in tools_in_module(module):
            specs.append(fn._gsmcp_spec)
    return sorted(specs, key=lambda spec: (spec.service, spec.name))


__all__ = ["MODULES", "Runtime", "all_specs", "register_all"]
