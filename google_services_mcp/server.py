"""Server assembly: build the MCP server, its runtime and the shared singletons."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from .audit import AuditLogger
from .client import GoogleApiClient
from .config import Settings
from .logging_setup import configure_logging, get_logger
from .permissions import PermissionPolicy
from .ratelimit import TokenBucket
from .tools import all_specs, register_all
from .tools.registry import Runtime

logger = get_logger(__name__)

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def build_runtime(settings: Settings, *, client: GoogleApiClient | None = None) -> Runtime:
    """Wire the single execution runtime shared by every tool."""
    configure_logging()
    return Runtime(
        settings,
        policy=PermissionPolicy(settings),
        audit=AuditLogger(settings.audit, buffer_size=settings.buffer.max_events),
        client=client,
        limiter=TokenBucket(settings.limits.requests_per_minute),
    )


def build_server(settings: Settings, *, runtime: Runtime | None = None) -> MCPServer:
    """Create the MCP server with every tool registered (policy gated at call time)."""
    server = MCPServer(
        name=settings.server_name,
        version=settings.server_version,
        instructions=settings.instructions,
    )
    active_runtime = runtime or build_runtime(settings)
    registered = register_all(server, active_runtime)
    logger.info(
        "server ready: %s tools, mode=%s, transport=%s",
        len(registered),
        settings.permissions.mode.value,
        settings.transport.type,
    )
    server.gsmcp_runtime = active_runtime
    server.gsmcp_tools = registered
    server.gsmcp_specs = all_specs()
    return server


def run(settings: Settings) -> None:
    """Run the MCP server over the configured transport (blocking)."""
    server = build_server(settings)
    transport = settings.transport
    if transport.type == "stdio":
        server.run("stdio")
        return

    if transport.host not in LOOPBACK_HOSTS:
        logger.warning(
            "streamable-http bound to %s; put an authenticating proxy in front of it",
            transport.host,
        )
    logger.info(
        "streamable-http listening on http://%s:%s%s",
        transport.host,
        transport.port,
        transport.path,
    )
    options: dict[str, Any] = {
        "host": transport.host,
        "port": transport.port,
        "streamable_http_path": transport.path,
        "json_response": transport.json_response,
    }
    if transport.allowed_hosts:
        from mcp.server.transport_security import TransportSecuritySettings

        options["transport_security"] = TransportSecuritySettings(
            allowed_hosts=list(transport.allowed_hosts),
            allowed_origins=[f"http://{host}:{transport.port}" for host in transport.allowed_hosts if ":" not in host],
        )
    server.run("streamable-http", **options)
