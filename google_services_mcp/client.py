"""Authorised Google API client factory with timeouts and cached discovery docs."""

from __future__ import annotations

import threading
from typing import Any

import httplib2
from google.auth.credentials import Credentials
from googleapiclient.discovery import build

from .config import Settings
from .exceptions import UnsupportedOperationError
from .logging_setup import get_logger
from .oauth.scopes import require_scopes
from .oauth.token_manager import TokenManager
from .retry import execute_with_retry

logger = get_logger("client")

API_VERSIONS: dict[str, str] = {
    "drive": "v3",
    "sheets": "v4",
    "gmail": "v1",
    "calendar": "v3",
    "docs": "v1",
}

# Default scopes each service needs so the client fails early with a clear message.
DEFAULT_SCOPES: dict[str, list[str]] = {
    "drive": ["https://www.googleapis.com/auth/drive.readonly"],
    "sheets": ["https://www.googleapis.com/auth/spreadsheets.readonly"],
    "gmail": ["https://www.googleapis.com/auth/gmail.readonly"],
    "calendar": ["https://www.googleapis.com/auth/calendar.readonly"],
    "docs": ["https://www.googleapis.com/auth/documents.readonly"],
}


class GoogleApiClient:
    """Builds and caches discovery clients.

    ``build()`` is slow (it parses the discovery document), so clients are cached
    per (api, version). Discovery is fetched from a local cache when available and
    never from disk on every call.
    """

    def __init__(self, settings: Settings, tokens: TokenManager, *, build_func: Any = build) -> None:
        self.settings = settings
        self.tokens = tokens
        self._build_func = build_func
        self._clients: dict[str, Any] = {}
        self._lock = threading.Lock()

    # -- credential plumbing ------------------------------------------------
    def credentials(self, *, force_refresh: bool = False) -> Credentials:
        return self.tokens.get_credentials(force_refresh=force_refresh)

    def http(self) -> httplib2.Http:
        creds = self.credentials()
        http = creds.authorize(httplib2.Http(timeout=self.settings.google.timeout_seconds))
        # Ensure an expired token is refreshed transparently on retry.
        if hasattr(http, "refresh_credentials"):
            http.refresh_credentials = creds
        http.user_agent = self.settings.google.user_agent
        return http

    def service(self, api: str, *, required_scopes: list[str] | None = None) -> Any:
        if api not in API_VERSIONS:
            raise UnsupportedOperationError(f"Unknown Google API `{api}`.")
        if required_scopes:
            require_scopes(required_scopes, self.tokens.granted_scopes())
        with self._lock:
            cached = self._clients.get(api)
            if cached is not None:
                return cached
            version = API_VERSIONS[api]
            try:
                client = self._build_func(
                    api,
                    version,
                    http=self.http(),
                    cache_discovery=True,
                    static_discovery=False,
                )
            except Exception as exc:  # noqa: BLE001 - normalised for callers
                from .exceptions import map_upstream_error

                raise map_upstream_error(exc) from exc
            self._clients[api] = client
            logger.info("built Google API client", extra={"context": {"api": api, "version": version}})
            return client

    def invalidate(self) -> None:
        with self._lock:
            self._clients.clear()

    # -- typed shortcuts ----------------------------------------------------
    def drive(self, required_scopes: list[str] | None = None) -> Any:
        return self.service("drive", required_scopes=required_scopes)

    def sheets(self, required_scopes: list[str] | None = None) -> Any:
        return self.service("sheets", required_scopes=required_scopes)

    def gmail(self, required_scopes: list[str] | None = None) -> Any:
        return self.service("gmail", required_scopes=required_scopes)

    def calendar(self, required_scopes: list[str] | None = None) -> Any:
        return self.service("calendar", required_scopes=required_scopes)

    def docs(self, required_scopes: list[str] | None = None) -> Any:
        return self.service("docs", required_scopes=required_scopes)

    # -- request execution --------------------------------------------------
    def execute(self, request: Any, *, idempotent: bool = True) -> Any:
        return execute_with_retry(
            request,
            max_retries=self.settings.google.max_retries,
            base_delay=self.settings.google.backoff_base_seconds,
            max_delay=self.settings.google.backoff_max_seconds,
            idempotent=idempotent,
        )
