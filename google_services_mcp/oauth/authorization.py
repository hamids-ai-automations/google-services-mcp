"""Interactive and headless OAuth authorization flows."""

from __future__ import annotations

from typing import Any

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow, InstalledAppFlow

from ..config import OAuthSettings
from ..exceptions import AuthenticationError, ConfigurationError
from ..logging_setup import get_logger
from ..security import redact
from .token_manager import TokenManager

logger = get_logger("oauth.authorization")


def _flow(manager: TokenManager, scopes: list[str]) -> InstalledAppFlow:
    config = manager.client_config()
    try:
        return InstalledAppFlow.from_client_config(config, scopes=scopes)
    except Exception as exc:  # noqa: BLE001 - library raises several types
        raise ConfigurationError(f"Could not initialise the OAuth flow: {exc}") from exc


def run_local_server_login(
    settings: OAuthSettings,
    scopes: list[str],
    *,
    port: int = 0,
    open_browser: bool = True,
    timeout_seconds: int = 300,
) -> Credentials:
    """Loopback flow. Best for a desktop machine with a browser."""
    manager = TokenManager(settings)
    flow = _flow(manager, scopes)
    try:
        creds = flow.run_local_server(
            port=port,
            open_browser=open_browser,
            authorization_prompt_message="Open this URL to authorise Google Services MCP:\n{url}",
            success_message="Authorisation complete. You can close this tab.",
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        raise AuthenticationError(
            "Browser-based authorisation failed. Try `auth login --console` on a headless machine.",
            details={"reason": type(exc).__name__},
        ) from exc
    if not creds or not creds.token:
        raise AuthenticationError("Authorisation did not return an access token.")
    manager.save(creds)
    logger.info("oauth login complete", extra={"context": {"scopes": len(scopes)}})
    return creds


def run_console_login(settings: OAuthSettings, scopes: list[str]) -> Credentials:
    """Out-of-band flow for machines without a browser (prints a URL, reads a code)."""
    manager = TokenManager(settings)
    flow = _flow(manager, scopes)
    try:
        creds = flow.run_console(
            authorization_prompt_message="1) Open this URL in any browser:\n{url}\n2) Paste the code here: "
        )
    except Exception as exc:  # noqa: BLE001
        raise AuthenticationError("Console authorisation failed.", details={"reason": type(exc).__name__}) from exc
    if not creds or not creds.token:
        raise AuthenticationError("Authorisation did not return an access token.")
    manager.save(creds)
    return creds


def authorization_url(settings: OAuthSettings, scopes: list[str], *, redirect_uri: str | None = None) -> dict[str, Any]:
    """Build an offline authorisation URL (for remote/UI-driven consent flows)."""
    manager = TokenManager(settings)
    config = manager.client_config()
    client_section = config.get("installed") or config.get("web") or {}
    if not client_section.get("client_id"):
        raise ConfigurationError("Client secrets file is missing client_id.")
    flow: Flow = InstalledAppFlow.from_client_config(config, scopes=scopes)
    flow.redirect_uri = redirect_uri or settings.redirect_uri
    url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return {"authorization_url": url, "state": state, "redirect_uri": flow.redirect_uri, "scopes": scopes}


def exchange_authorization_code(
    settings: OAuthSettings,
    scopes: list[str],
    code: str,
    *,
    redirect_uri: str | None = None,
    state: str | None = None,
) -> dict[str, Any]:
    manager = TokenManager(settings)
    flow = _flow(manager, scopes)
    flow.redirect_uri = redirect_uri or settings.redirect_uri
    try:
        flow.fetch_token(code=code, state=state)
    except Exception as exc:  # noqa: BLE001
        raise AuthenticationError(
            "The authorization code could not be exchanged.", details={"reason": str(exc)[:200]}
        ) from exc
    creds = flow.credentials
    manager.save(creds)
    return {"status": "authorized", "scopes": list(creds.scopes or scopes), "expiry": str(creds.expiry)}


def revoke_access(settings: OAuthSettings) -> dict[str, Any]:
    """Revoke the stored token at Google and delete the local copy."""
    import requests

    manager = TokenManager(settings)
    status = manager.status()
    if not status.token_present:
        return {"revoked": False, "message": "No local token to revoke."}
    try:
        creds = manager.get_credentials(force_refresh=False)
        token = creds.refresh_token or creds.token
    except AuthenticationError:
        token = None
    revoked = False
    if token:
        try:
            response = requests.post(
                "https://oauth2.googleapis.com/revoke",
                data={"token": token},
                headers={"content-type": "application/x-www-form-urlencoded"},
                timeout=15,
            )
            revoked = response.status_code == 200
        except requests.RequestException as exc:
            logger.warning("token revoke request failed: %s", type(exc).__name__)
    path = settings.token_path()
    if path and path.exists():
        path.unlink(missing_ok=True)
    return {"revoked": revoked, "local_token_deleted": True, "message": redact("token removed")}


def describe_login_state(settings: OAuthSettings) -> dict[str, Any]:
    manager = TokenManager(settings)
    status = manager.status()
    return status.as_dict()
