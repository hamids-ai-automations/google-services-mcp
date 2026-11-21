"""Command line interface: ``serve``, ``auth``, ``policy`` and ``doctor``."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .audit import AuditLogger
from .config import Settings
from .exceptions import GoogleServicesMCPError
from .logging_setup import configure_logging, get_logger
from .oauth import authorization
from .oauth import scopes as scope_catalog
from .oauth.token_manager import TokenManager
from .permissions import PermissionPolicy
from .server import run as run_server

logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="google-services-mcp",
        description="Permission-controlled MCP gateway for Google Drive, Sheets, Gmail, Calendar and Docs.",
    )
    parser.add_argument("--config", help="Path to config.yaml (defaults to config/config.yaml or $GSMCP_CONFIG).")
    subparsers = parser.add_subparsers(dest="command", required=False)

    subparsers.add_parser("serve", help="Run the MCP server.")

    auth = subparsers.add_parser("auth", help="Manage the Google OAuth credential.")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    login = auth_sub.add_parser("login", help="Authorise a Google account.")
    login.add_argument("--console", action="store_true", help="Headless flow: print the URL and paste the code.")
    login.add_argument("--no-browser", action="store_true", help="Print the consent URL instead of opening a browser.")
    login.add_argument("--code", help="Authorization code returned by the consent screen.")
    login.add_argument("--scopes", nargs="*", default=None, help="Explicit scope keys or URLs.")
    login.add_argument("--write", action="store_true", help="Request write scopes as well as read scopes.")
    login.add_argument("--port", type=int, default=0, help="Local callback port (0 = ephemeral).")
    login.add_argument("--timeout", type=int, default=300, help="Seconds to wait for the browser callback.")
    auth_sub.add_parser("status", help="Show credential state (never prints tokens).")
    auth_sub.add_parser("logout", help="Revoke the token at Google and delete it locally.")

    subparsers.add_parser("policy", help="Print the effective permission matrix.")
    subparsers.add_parser("doctor", help="Run local diagnostics (config, credential, services).")
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = Settings.load(args.config)
    except GoogleServicesMCPError as exc:
        return _fail(exc)

    command = args.command or "serve"
    try:
        if command == "serve":
            run_server(settings)
            return 0
        if command == "auth":
            return _handle_auth(settings, args)
        if command == "policy":
            return _print(PermissionPolicy(settings).summary())
        if command == "doctor":
            return _handle_doctor(settings)
    except GoogleServicesMCPError as exc:
        return _fail(exc)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    parser.print_help()
    return 2


# -- commands --------------------------------------------------------------
def _handle_auth(settings: Settings, args: argparse.Namespace) -> int:
    if args.auth_command == "status":
        state = authorization.describe_login_state(settings.oauth)
        manager = TokenManager(settings.oauth)
        state["granted_scopes"] = sorted(manager.granted_scopes())
        state["missing_default_scopes"] = sorted(
            scope_catalog.missing_scopes(scope_catalog.default_login_scopes(True), manager.granted_scopes())
        )
        return _print(state)

    if args.auth_command == "logout":
        return _print(authorization.revoke_access(settings.oauth))

    requested = args.scopes or scope_catalog.default_login_scopes(args.write)
    requested = scope_catalog.resolve_scopes(requested) if args.scopes else requested

    if args.code:
        return _print(authorization.exchange_authorization_code(settings.oauth, requested, args.code))

    if args.no_browser and not args.console:
        payload = authorization.authorization_url(settings.oauth, requested)
        payload["next_step"] = "Open authorization_url, then run `auth login --code <code>`."
        return _print(payload)

    if args.console:
        credentials = authorization.run_console_login(settings.oauth, requested)
    else:
        credentials = authorization.run_local_server_login(
            settings.oauth,
            requested,
            port=args.port,
            open_browser=not args.no_browser,
            timeout_seconds=args.timeout,
        )
    return _print(
        {
            "status": "authorized",
            "scopes": list(credentials.scopes or requested),
            "expiry": str(credentials.expiry),
        }
    )


def _handle_doctor(settings: Settings) -> int:
    manager = TokenManager(settings.oauth)
    status = manager.status()
    audit = AuditLogger(settings.audit, buffer_size=settings.buffer.max_events)
    secrets_path = settings.oauth.secrets_path()
    token_path = settings.oauth.token_path()
    report: dict[str, Any] = {
        "config": settings.describe(),
        "oauth": status.as_dict(),
        "paths_configured": {
            "client_secrets": bool(settings.oauth.client_secrets_file),
            "token_file": bool(settings.oauth.token_file),
            "download_dir": str(settings.download_dir()),
        },
        "files_exist": {
            "client_secrets": bool(secrets_path and secrets_path.exists()),
            "token": bool(token_path and token_path.exists()),
        },
        "services": sorted(settings.enabled_services()),
        "allowed_tools": PermissionPolicy(settings).allowed_names(_tool_specs()),
        "audit": audit.stats(),
        "python": sys.version.split()[0],
    }
    return _print(report)


def _tool_specs() -> list[Any]:
    from .tools import MODULES
    from .tools.registry import tools_in_module

    specs = []
    for module in MODULES:
        for fn in tools_in_module(module):
            specs.append(fn._gsmcp_spec)
    return specs


def _print(payload: Any) -> int:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0


def _fail(exc: GoogleServicesMCPError) -> int:
    print(json.dumps({"error": exc.to_payload()}, indent=2), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
