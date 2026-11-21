"""Token storage, refresh and scope introspection."""

from __future__ import annotations

import contextlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials

from ..config import OAuthSettings
from ..exceptions import AuthenticationError, ConfigurationError, InvalidTokenError
from ..logging_setup import get_logger

logger = get_logger("oauth.tokens")

REFRESH_MARGIN_SECONDS = 120


@dataclass
class TokenStatus:
    configured: bool
    token_present: bool
    valid: bool
    expired: bool
    has_refresh_token: bool
    scopes: list[str] = field(default_factory=list)
    expiry: str | None = None
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "token_present": self.token_present,
            "valid": self.valid,
            "expired": self.expired,
            "has_refresh_token": self.has_refresh_token,
            "scopes": self.scopes,
            "expiry": self.expiry,
            "message": self.message,
        }


class TokenManager:
    """Loads, refreshes and persists user OAuth credentials.

    The token file is written with owner-only permissions on POSIX. Tokens are
    never logged or included in tool responses.
    """

    def __init__(
        self,
        settings: OAuthSettings,
        *,
        clock: Callable[[], float] = time.time,
        request_factory: Callable[[], Any] = GoogleAuthRequest,
    ) -> None:
        self.settings = settings
        self._clock = clock
        self._request_factory = request_factory
        self._cached: Credentials | None = None

    # -- paths --------------------------------------------------------------
    @property
    def token_path(self) -> Path:
        path = self.settings.token_path()
        if path is None:
            raise ConfigurationError("oauth.token_file is not configured.")
        return path

    @property
    def client_secrets_path(self) -> Path:
        path = self.settings.secrets_path()
        if path is None:
            raise ConfigurationError("oauth.client_secrets_file is not configured.")
        return path

    def client_config(self) -> dict[str, Any]:
        path = self.client_secrets_path
        if not path.exists():
            raise ConfigurationError(
                f"OAuth client secrets file not found at {path}. "
                "Download it from Google Cloud Console > APIs & Services > Credentials."
            )
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"OAuth client secrets file is unreadable: {exc}") from exc
        if not any(key in config for key in ("installed", "web")):
            raise ConfigurationError("Client secrets file must contain an 'installed' or 'web' section.")
        # Held in memory only; never logged, never returned by a tool.
        return config

    # -- status -------------------------------------------------------------
    def status(self) -> TokenStatus:
        configured = bool(self.settings.client_secrets_file and self.settings.token_file)
        if not configured:
            return TokenStatus(False, False, False, False, False, message="OAuth paths are not configured.")
        path = self.settings.token_path()
        if path is None or not path.exists():
            return TokenStatus(True, False, False, False, False, message="No token yet; run `auth login`.")
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return TokenStatus(True, True, False, True, False, message=f"Token file unreadable: {exc}")
        expiry_raw = info.get("expiry")
        expired = True
        if info.get("expiry"):
            try:
                from datetime import datetime

                expiry_dt = datetime.fromisoformat(str(info["expiry"]).replace("Z", "+00:00"))
                expired = expiry_dt.timestamp() - REFRESH_MARGIN_SECONDS <= self._clock()
            except ValueError:
                expired = True
        elif info.get("token"):
            expired = False
        has_refresh = bool(info.get("refresh_token"))
        return TokenStatus(
            configured=True,
            token_present=True,
            valid=bool(info.get("token")) and (not expired or has_refresh),
            expired=expired,
            has_refresh_token=has_refresh,
            scopes=list(info.get("scopes") or []),
            expiry=str(expiry_raw) if expiry_raw else None,
            message="ok" if not expired or has_refresh else "Access token expired and no refresh token available.",
        )

    def granted_scopes(self) -> set[str]:
        status = self.status()
        return set(status.scopes)

    def has_credentials(self) -> bool:
        status = self.status()
        return status.token_present and status.valid

    # -- credentials --------------------------------------------------------
    def get_credentials(self, *, force_refresh: bool = False) -> Credentials:
        if self._cached is not None and not force_refresh and not self._cached.expired:
            return self._cached
        path = self.token_path
        if not path.exists():
            raise AuthenticationError(
                "No Google token found. Run `google-services-mcp auth login` first.",
                details={"token_file": str(path)},
            )
        try:
            creds = Credentials.from_authorized_user_file(str(path))
        except (ValueError, OSError) as exc:
            raise InvalidTokenError(f"Stored Google token is unreadable or malformed: {exc}") from exc

        needs_refresh = force_refresh or creds.expired or not creds.token
        if needs_refresh:
            if not creds.refresh_token:
                raise InvalidTokenError(
                    "Access token expired and no refresh token is stored. Re-run `google-services-mcp auth login`."
                )
            try:
                creds.refresh(self._request_factory())
            except RefreshError as exc:
                raise InvalidTokenError(
                    "Google rejected the refresh token (revoked, expired or password changed). "
                    "Re-run `google-services-mcp auth login`."
                ) from exc
            self.save(creds)
        self._cached = creds
        return creds

    def save(self, creds: Credentials) -> None:
        path = self.token_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.loads(creds.to_json())
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        with contextlib.suppress(OSError, NotImplementedError):  # pragma: no cover - Windows
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        self._cached = creds
        logger.info("stored refreshed Google token", extra={"context": {"token_file": str(path)}})
