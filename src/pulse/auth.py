"""OAuth for an installed (Desktop) app: loopback redirect + PKCE, token stored 0600."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from pulse.config import SCOPES, Settings
from pulse.fileio import is_private, write_private

log = logging.getLogger(__name__)

AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"  # noqa: S105 - endpoint URL, not a secret


class AuthError(RuntimeError):
    """No usable credentials; the user must run ``pulse auth`` again."""


class TokenStore:
    """Persists authorized-user credentials as JSON at a 0600 path."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> Credentials | None:
        if not self.path.exists():
            return None
        if not is_private(self.path):
            log.warning("token file had loose permissions; tightening to 0600")
            self.path.chmod(0o600)
        info = json.loads(self.path.read_text())
        creds: Credentials = Credentials.from_authorized_user_info(info, scopes=list(SCOPES))
        return creds

    def save(self, creds: Credentials) -> None:
        payload: dict[str, Any] = json.loads(creds.to_json())
        payload["saved_at"] = datetime.now(UTC).isoformat()
        write_private(self.path, json.dumps(payload, indent=2))

    def delete(self) -> None:
        self.path.unlink(missing_ok=True)


def client_config(settings: Settings) -> dict[str, Any]:
    if not settings.google_client_id or not settings.google_client_secret.get_secret_value():
        raise AuthError(
            "PULSE_GOOGLE_CLIENT_ID / PULSE_GOOGLE_CLIENT_SECRET are not set (see docs/SETUP.md)."
        )
    return {
        "installed": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret.get_secret_value(),
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
            "redirect_uris": ["http://127.0.0.1"],
        }
    }


def run_consent_flow(settings: Settings, port: int, print_fn: Callable[[str], None]) -> Credentials:
    """Run the loopback consent flow without opening a browser (headless server friendly)."""
    from google_auth_oauthlib.flow import InstalledAppFlow  # heavy import, CLI-only

    flow = InstalledAppFlow.from_client_config(
        client_config(settings), scopes=list(SCOPES), autogenerate_code_verifier=True
    )
    # PKCE S256 is used because a code_verifier is auto-generated; oauthlib validates `state`.
    creds: Credentials = flow.run_local_server(
        host="127.0.0.1",
        bind_addr=settings.oauth_bind_addr,
        port=port,
        open_browser=False,
        authorization_prompt_message=(
            "Open this URL in a browser on the machine that forwards port "
            f"{port} (see docs/SETUP.md):\n\n{{url}}\n"
        ),
        success_message="Pulse is authorized. You can close this tab.",
        access_type="offline",
        prompt="consent",  # guarantees a refresh token is issued
        include_granted_scopes="false",
    )
    if not creds.refresh_token:
        raise AuthError("Google did not return a refresh token; re-run `pulse auth`.")
    print_fn("Authorization complete.")
    return creds


def missing_scopes(creds: Credentials) -> list[str]:
    """Scopes we asked for that the user did not grant (granular consent allows unticking)."""
    granted = set(creds.granted_scopes or creds.scopes or [])
    return [s for s in SCOPES if s not in granted]


class CredentialManager:
    """Hands out valid access tokens, refreshing and re-persisting as needed. Thread-safe."""

    def __init__(self, store: TokenStore, request_factory: Callable[[], Any] = Request) -> None:
        self.store = store
        self._request_factory = request_factory
        self._creds: Credentials | None = None
        self._lock = threading.Lock()

    def _load(self) -> Credentials:
        if self._creds is None:
            self._creds = self.store.load()
        if self._creds is None:
            raise AuthError("Not authorized yet: run `pulse auth`.")
        return self._creds

    def access_token(self, force_refresh: bool = False) -> str:
        with self._lock:
            creds = self._load()
            if force_refresh or not creds.valid:
                self._refresh(creds)
            token = creds.token
            if not isinstance(token, str):
                raise AuthError("Refresh did not yield an access token: run `pulse auth`.")
            return token

    def _refresh(self, creds: Credentials) -> None:
        if not creds.refresh_token:
            raise AuthError("Stored credentials have no refresh token: run `pulse auth`.")
        try:
            creds.refresh(self._request_factory())
        except RefreshError as exc:
            # Do not include exc details verbatim: they can echo request bodies.
            raise AuthError(
                "Token refresh failed (revoked, expired, or app in Testing mode): run `pulse auth`."
            ) from exc
        self.store.save(creds)
        log.info("access token refreshed")
