from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from pulse import prefs, security
from pulse.api.app import create_app
from pulse.config import Settings
from pulse.db import make_engine, make_session_factory, migrate
from pulse.models import DailyMetric, IntradaySteps, SyncState
from pulse.sync.engine import SyncEngine
from tests.fakeapi import FakeApi

TZ = ZoneInfo("America/Toronto")
TODAY = date(2026, 11, 21)
NOW = datetime(2026, 11, 21, 17, 0, tzinfo=UTC)


def _seed(sessions) -> None:
    api = FakeApi()
    for i in range(6):
        d = TODAY - timedelta(days=i)
        api.steps[d] = 8000
        api.resting_hr[d] = 60
        api.sleep[f"s{i}"] = (
            datetime(d.year, d.month, d.day, 4, 0, tzinfo=UTC) - timedelta(hours=1),
            datetime(d.year, d.month, d.day, 12, 0, tzinfo=UTC),
        )
    assert SyncEngine(sessions, api.client(), TZ, now=lambda: NOW).run_sync().ok
    with sessions() as s:
        # 28 days of history for baselines (outside the sync window).
        for i in range(4, 33):
            d = TODAY - timedelta(days=i)
            s.merge(DailyMetric(civil_date=d, metric="resting_hr", value=55 + (i % 5), unit="bpm"))
            s.merge(DailyMetric(civil_date=d, metric="steps", value=7000 + 100 * i, unit="count"))
            for h in (8, 12, 18):
                s.merge(
                    IntradaySteps(
                        ts_utc=datetime(d.year, d.month, d.day, h + 5, tzinfo=UTC),
                        civil_date=d,
                        steps=1000,
                    )
                )
        s.merge(
            IntradaySteps(
                ts_utc=datetime(2026, 11, 21, 13, tzinfo=UTC), civil_date=TODAY, steps=2500
            )
        )
        s.commit()


@pytest.fixture
def app_env(tmp_path):
    settings = Settings(
        data_dir=tmp_path / "data",
        static_dir=tmp_path / "dist",
        scheduler_enabled=False,
        _env_file=None,
    )  # type: ignore[call-arg]
    engine = make_engine(None)
    migrate(engine)
    sessions = make_session_factory(engine)
    _seed(sessions)
    app = create_app(settings, engine=engine, start_scheduler=False, now=lambda: NOW)
    return app, sessions, settings


@pytest.fixture
def client(app_env):
    with TestClient(app_env[0]) as c:
        yield c


def test_health_and_openapi_operation_ids(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"
    spec = client.get("/api/v1/openapi.json").json()
    ops = {op["operationId"] for p in spec["paths"].values() for op in p.values()}
    assert {
        "get_today",
        "get_status",
        "get_metric",
        "get_sleep",
        "get_sleep_trend",
        "get_intraday_heart_rate",
        "trigger_sync",
    } <= ops


def test_today(client):
    body = client.get("/api/v1/today").json()
    assert body["date"] == "2026-11-21"
    tiles = {t["key"]: t for t in body["tiles"]}
    assert list(tiles) == ["readiness", "sleep_main_min", "resting_hr", "hrv_rmssd", "steps", "azm"]
    rhr = tiles["resting_hr"]
    assert rhr["value"] == 60 and rhr["baseline"]["n"] == 28
    assert rhr["status"] in {"in_range", "mild", "notable"}
    assert len(rhr["spark"]) == 14 and rhr["spark"][-1] == {"date": "2026-11-21", "value": 60.0}
    steps = tiles["steps"]
    # So-far baseline: by noon local, previous days had 2 of 3 slots (08:00, 12:00) = 2000.
    assert steps["baseline"]["median"] == 2000
    assert steps["goal"] == 10_000
    assert tiles["readiness"]["value"] is None
    curve = body["steps_curve"]
    assert len(curve["today"]) == 96 and curve["today"][-1] is None  # future slots are null
    assert curve["days_in_median"] == 25  # seeded intraday history inside the 28-day window
    assert body["last_synced"] is not None


def test_metrics_aggregation(client):
    week = client.get("/api/v1/metrics/steps?from=2026-11-16&to=2026-11-22&granularity=week").json()
    # Monday-based week, summed: 4 synced days x 8000 + seeded 11-16 (7500) and 11-17 (7400).
    assert week["points"] == [{"date": "2026-11-16", "value": 4 * 8000.0 + 7500 + 7400}]
    rhr = client.get("/api/v1/metrics/resting_hr?from=2026-11-16&to=2026-11-21&granularity=week")
    assert rhr.json()["points"][0]["value"] == 59  # averaged: (4 x 60 + 59 + 55) / 6
    month = client.get("/api/v1/metrics/steps?from=2026-11-01&to=2026-11-21&granularity=month")
    assert month.json()["points"][0]["date"] == "2026-11-01"
    assert client.get("/api/v1/metrics/nope").status_code == 404
    assert client.get("/api/v1/metrics/steps?from=2026-11-21&to=2026-11-01").status_code == 422


def test_sleep_endpoints(client):
    night = client.get("/api/v1/sleep").json()
    assert night["date"] == "2026-11-21" and night["session"]["stages"]
    assert night["prev_date"] == "2026-11-20" and night["next_date"] is None
    assert night["goal_min"] == 480
    empty = client.get("/api/v1/sleep?date=2026-01-01").json()
    assert empty["session"] is None
    trend = client.get("/api/v1/sleep/trend?from=2026-11-15&to=2026-11-21").json()
    assert len(trend["nights"]) == 4  # the sync window
    assert trend["consistency"]["nights"] == 4


def test_status_reports_missing_token_and_streams(client):
    body = client.get("/api/v1/status").json()
    assert body["auth"]["ok"] is False and "pulse auth" in body["auth"]["error"]
    assert {s["stream"] for s in body["streams"]} >= {"daily_rollups_90", "sleep"}
    assert any(m["key"] == "steps" for m in body["metrics"])
    assert body["syncing"] is False


def test_status_auth_error_surfaces(app_env, client):
    _, sessions, settings = app_env
    settings.token_path.parent.mkdir(parents=True, exist_ok=True)
    settings.token_path.write_text("{}")
    with sessions() as s:
        row = s.get(SyncState, "_auth")
        row.last_error = "Token refresh failed"
        s.commit()
    auth = client.get("/api/v1/status").json()["auth"]
    assert auth == {"ok": False, "error": "Token refresh failed", "checked_at": auth["checked_at"]}


def test_manual_sync_without_scheduler(client):
    assert client.post("/api/v1/sync").status_code == 503


def test_passcode_gate(app_env, client):
    _, sessions, _ = app_env
    assert client.get("/api/v1/session").json() == {
        "passcode_required": False,
        "authenticated": True,
    }
    with sessions() as s:
        prefs.put(s, "passcode_hash", security.hash_passcode("2468"))
        s.commit()
    assert client.get("/api/v1/today").status_code == 401
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/session").json()["authenticated"] is False
    assert client.post("/api/v1/session", json={"passcode": "12"}).status_code == 422
    assert client.post("/api/v1/session", json={"passcode": "1111"}).status_code == 401
    assert client.post("/api/v1/session", json={"passcode": "2468"}).status_code == 204
    assert client.get("/api/v1/today").status_code == 200
    client.delete("/api/v1/session")
    assert client.get("/api/v1/today").status_code == 401


def test_passcode_rate_limit(app_env, client):
    _, sessions, _ = app_env
    with sessions() as s:
        prefs.put(s, "passcode_hash", security.hash_passcode("2468"))
        s.commit()
    codes = [
        client.post("/api/v1/session", json={"passcode": "0000"}).status_code for _ in range(6)
    ]
    assert codes == [401] * 5 + [429]
    assert client.post("/api/v1/session", json={"passcode": "2468"}).status_code == 429


def test_changing_passcode_invalidates_sessions(app_env, client):
    _, sessions, _ = app_env
    with sessions() as s:
        prefs.put(s, "passcode_hash", security.hash_passcode("2468"))
        s.commit()
    client.post("/api/v1/session", json={"passcode": "2468"})
    assert client.get("/api/v1/today").status_code == 200
    with sessions() as s:
        prefs.put(s, "passcode_hash", security.hash_passcode("1357"))
        s.commit()
    assert client.get("/api/v1/today").status_code == 401


def test_spa_serving(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Pulse</title>")
    (dist / "assets" / "app-abc123.js").write_text("console.log(1)")
    (dist / "sw.js").write_text("// sw")
    (tmp_path / "secret.txt").write_text("nope")
    settings = Settings(data_dir=tmp_path / "data", static_dir=dist, _env_file=None)  # type: ignore[call-arg]
    engine = make_engine(None)
    app = create_app(settings, engine=engine, start_scheduler=False)
    with TestClient(app) as c:
        assert "Pulse" in c.get("/").text
        assert "Pulse" in c.get("/sleep").text  # client-side route
        asset = c.get("/assets/app-abc123.js")
        assert "immutable" in asset.headers["cache-control"]
        assert c.get("/sw.js").headers["cache-control"] == "no-cache"
        assert "nope" not in c.get("/..%2Fsecret.txt").text
        assert c.get("/api/v1/does-not-exist").status_code == 404


def test_migrations_match_models(tmp_path):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from pulse.models import Base

    engine = make_engine(tmp_path / "m.db")
    migrate(engine)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
    with engine.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
    assert mode == "wal"
    assert select  # keep import used
