"""Compact widget snapshot for the Android home-screen widget."""

from __future__ import annotations

import json

from tests.test_api import TODAY, app_env, client  # noqa: F401 - pytest fixtures

API = "/api/v1"


def test_widget_snapshot(client):  # noqa: F811
    r = client.get(f"{API}/widget")
    assert r.status_code == 200
    body = r.json()
    assert body["date"] == TODAY.isoformat()
    assert body["steps_goal"] == 10_000 and body["sleep_goal_min"] == 480
    assert body["azm_goal"] == 150
    assert body["readiness"]["status"] in {"in_range", "mild", "notable", "none"}
    assert body["readiness"]["label"]
    assert body["auth_ok"] is False  # no token file in the test settings
    assert body["last_synced"] is not None
    assert len(json.dumps(body)) < 700  # small enough for a battery-friendly widget


def test_widget_needs_passcode(client):  # noqa: F811
    client.put(f"{API}/settings/passcode", json={"new": "2468"})
    client.cookies.clear()
    assert client.get(f"{API}/widget").status_code == 401
