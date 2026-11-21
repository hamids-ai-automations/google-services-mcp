"""OAuth 2.0 primitives for the gateway (least-privilege, refreshable, revocable)."""

from .authorization import (
    authorization_url,
    describe_login_state,
    exchange_authorization_code,
    revoke_access,
    run_console_login,
    run_local_server_login,
)
from .scopes import (
    SCOPE_CATALOG,
    default_login_scopes,
    missing_scopes,
    require_scopes,
    resolve_scopes,
    satisfied_by,
)
from .token_manager import TokenManager, TokenStatus

__all__ = [
    "SCOPE_CATALOG",
    "TokenManager",
    "TokenStatus",
    "authorization_url",
    "default_login_scopes",
    "describe_login_state",
    "exchange_authorization_code",
    "missing_scopes",
    "require_scopes",
    "resolve_scopes",
    "revoke_access",
    "run_console_login",
    "run_local_server_login",
    "satisfied_by",
]
