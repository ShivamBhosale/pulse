"""Wiring shared by the CLI and the web app."""

from __future__ import annotations

from pulse.auth import CredentialManager, TokenStore
from pulse.client import HealthClient
from pulse.config import Settings


def make_client(settings: Settings) -> HealthClient:
    """A client with its own credential manager (re-reads token.json, so a fresh
    `pulse auth` takes effect on the next sync without restarting the server)."""
    creds = CredentialManager(TokenStore(settings.token_path))
    return HealthClient(
        lambda force: creds.access_token(force_refresh=force),
        base_url=settings.api_base,
        min_interval=settings.min_request_interval,
    )
