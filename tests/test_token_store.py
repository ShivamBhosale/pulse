import json
import logging

import pytest
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from pulse.auth import AuthError, CredentialManager, TokenStore, missing_scopes
from pulse.config import SCOPES
from pulse.logsetup import RedactingFilter, redact


def creds(token="ya29.access", refresh="1//refresh-token"):
    return Credentials(
        token=token,
        refresh_token=refresh,
        token_uri="https://oauth2.googleapis.com/token",
        client_id="cid.apps.googleusercontent.com",
        client_secret="GOCSPX-secret",
        scopes=list(SCOPES),
    )


def test_save_is_0600_and_roundtrips(tmp_path):
    store = TokenStore(tmp_path / "token.json")
    store.save(creds())
    assert (tmp_path / "token.json").stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".*.tmp"))
    loaded = store.load()
    assert loaded is not None and loaded.refresh_token == "1//refresh-token"


def test_load_tightens_loose_permissions(tmp_path):
    p = tmp_path / "token.json"
    TokenStore(p).save(creds())
    p.chmod(0o644)
    TokenStore(p).load()
    assert p.stat().st_mode & 0o777 == 0o600


def test_missing_token_raises_auth_error(tmp_path):
    mgr = CredentialManager(TokenStore(tmp_path / "token.json"))
    with pytest.raises(AuthError, match="pulse auth"):
        mgr.access_token()


class FakeRequest:
    pass


def test_refresh_saves_rotated_token(tmp_path, monkeypatch):
    store = TokenStore(tmp_path / "token.json")
    store.save(creds(token=None))

    def fake_refresh(self, request):
        self.token = "ya29.new"
        self.expiry = None

    monkeypatch.setattr(Credentials, "refresh", fake_refresh)
    mgr = CredentialManager(store, request_factory=FakeRequest)
    assert mgr.access_token() == "ya29.new"
    assert json.loads((tmp_path / "token.json").read_text())["token"] == "ya29.new"


def test_refresh_failure_becomes_auth_error(tmp_path, monkeypatch):
    store = TokenStore(tmp_path / "token.json")
    store.save(creds(token=None))

    def boom(self, request):
        raise RefreshError("invalid_grant: Token has been expired or revoked.")

    monkeypatch.setattr(Credentials, "refresh", boom)
    with pytest.raises(AuthError, match="refresh failed"):
        CredentialManager(store, request_factory=FakeRequest).access_token()


def test_missing_scopes_detects_unticked():
    c = creds()
    c._granted_scopes = list(SCOPES[:2])
    assert missing_scopes(c) == list(SCOPES[2:])


@pytest.mark.parametrize(
    "text",
    [
        "Authorization: Bearer ya29.a0AfH6SMBx",
        "refresh_token=1//0gAbCdEf",
        '{"client_secret": "GOCSPX-abc123"}',
        "code=4/0AbCd&state=xyz",
    ],
)
def test_redaction(text):
    out = redact(text)
    for secret in ("ya29.a0AfH6SMBx", "1//0gAbCdEf", "GOCSPX-abc123", "4/0AbCd"):
        assert secret not in out
    assert "[REDACTED]" in out


def test_redacting_filter_handles_args_and_extra_secrets():
    rec = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "token %s and %s", ("ya29.zzz", "mysecret"), None
    )
    RedactingFilter(("mysecret",)).filter(rec)
    assert "ya29.zzz" not in rec.getMessage() and "mysecret" not in rec.getMessage()
