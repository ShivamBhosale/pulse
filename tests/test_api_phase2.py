"""Phase 2 endpoints: readiness tile, settings, explore, activity, workouts, records, jobs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from pulse import derive
from pulse.models import DailyMetric, Exercise, HrZoneBound, IntradayHR
from tests.test_api import TODAY, app_env, client  # noqa: F401 - pytest fixtures

API = "/api/v1"


@pytest.fixture
def rich(app_env):  # noqa: F811
    """Add 40 days of HRV/sleep/AZM history, a workout with HR, then recompute derived."""
    _, sessions, _ = app_env
    with sessions() as s:
        for i in range(40):
            d = TODAY - timedelta(days=i)
            s.merge(DailyMetric(civil_date=d, metric="hrv_rmssd", value=40 + i % 4, unit="ms"))
            s.merge(DailyMetric(civil_date=d, metric="sleep_main_min", value=420.0, unit="min"))
            s.merge(DailyMetric(civil_date=d, metric="azm", value=float(10 + i % 7), unit="min"))
            s.merge(DailyMetric(civil_date=d, metric="steps", value=12_000.0, unit="count"))
        start = datetime(2026, 11, 20, 22, 0, tzinfo=UTC)
        s.add(
            Exercise(
                id="users/me/dataTypes/exercise/dataPoints/run1",
                civil_date=TODAY - timedelta(days=1),
                start_utc=start,
                end_utc=start + timedelta(minutes=5),
                exercise_type="RUNNING",
                name="Run",
                active_s=300,
                distance_m=1000,
                steps=900,
                kcal=60,
                avg_hr=140,
                source="FITBIT/Fitbit Air",
            )
        )
        for z, lo, hi in (("light", 90, 110), ("moderate", 111, 130), ("vigorous", 131, 160)):
            s.merge(
                HrZoneBound(civil_date=TODAY - timedelta(days=1), zone=z, min_bpm=lo, max_bpm=hi)
            )
        for m, bpm in enumerate((100, 120, 140, 145, 80)):
            s.add(
                IntradayHR(
                    ts_utc=start + timedelta(minutes=m),
                    civil_date=TODAY - timedelta(days=1),
                    bpm_avg=bpm,
                    bpm_min=bpm - 2,
                    bpm_max=bpm + 3,
                )
            )
        derive.recompute(s)
        s.commit()
    return app_env


def test_readiness_tile_has_breakdown_and_formula(rich, client):  # noqa: F811
    tiles = {t["key"]: t for t in client.get(f"{API}/today").json()["tiles"]}
    r = tiles["readiness"]
    assert r["value"] is not None and 0 <= r["value"] <= 100
    assert "not a medical measure" in r["formula"]
    assert "Personal heuristic" in r["note"]
    comps = {c["key"]: c for c in r["components"]}
    assert set(comps) == {"hrv", "rhr", "sleep", "strain"}
    assert comps["sleep"]["score"] == pytest.approx(87.5)  # 420 / 480
    assert sum(c["weight"] for c in comps.values()) == pytest.approx(1, abs=0.01)


def test_settings_roundtrip_recomputes_derived(rich, client):  # noqa: F811
    s = client.get(f"{API}/settings").json()
    assert s["goals"] == {"sleep_min": 480, "steps": 10000, "azm_weekly": 150}
    assert s["readiness_weights"] == {"hrv": 35, "rhr": 25, "sleep": 25, "strain": 15}
    assert s["units"] == "metric" and s["passcode_set"] is False

    def debt() -> float:
        pts = client.get(f"{API}/metrics/sleep_debt_min?from={TODAY}&to={TODAY}").json()
        return pts["points"][0]["value"]

    assert debt() == 7 * 60
    r = client.put(
        f"{API}/settings", json={"goals": {"sleep_min": 420, "steps": 8000, "azm_weekly": 150}}
    )
    assert r.status_code == 200 and r.json()["goals"]["steps"] == 8000
    assert debt() == 0

    assert client.put(f"{API}/settings", json={"units": "imperial"}).json()["units"] == "imperial"


@pytest.mark.parametrize(
    "body",
    [
        {"readiness_weights": {"hrv": 0, "rhr": 0, "sleep": 0, "strain": 0}},
        {"readiness_weights": {"hrv": -1, "rhr": 0, "sleep": 0, "strain": 0}},
        {"goals": {"sleep_min": 60, "steps": 8000, "azm_weekly": 150}},
        {"units": "furlongs"},
    ],
)
def test_settings_validation(client, body):  # noqa: F811
    assert client.put(f"{API}/settings", json=body).status_code == 422


def test_passcode_set_change_clear(client):  # noqa: F811
    url = f"{API}/settings/passcode"
    assert client.put(url, json={"new": "1234"}).status_code == 204
    assert client.get(f"{API}/session").json() == {
        "passcode_required": True,
        "authenticated": True,  # this device got a fresh session
    }
    assert client.put(url, json={"new": "5678"}).status_code == 401  # current required
    assert client.put(url, json={"current": "0000", "new": "5678"}).status_code == 401
    assert client.put(url, json={"current": "1234", "new": "5678"}).status_code == 204
    assert client.get(f"{API}/today").status_code == 200
    assert client.put(url, json={"current": "5678", "new": None}).status_code == 204
    assert client.get(f"{API}/session").json()["passcode_required"] is False


def test_series_band_weekday(rich, client):  # noqa: F811
    body = client.get(
        f"{API}/series", params={"metrics": ["steps", "azm"], "from": "2026-11-15"}
    ).json()
    assert [s["metric"] for s in body["series"]] == ["steps", "azm"]
    assert client.get(f"{API}/series", params={"metrics": ["nope"]}).status_code == 404

    m = client.get(f"{API}/metrics/hrv_rmssd?band=true&from=2026-11-15").json()
    assert len(m["band"]) == 7 and m["band"][0]["q1"] <= m["band"][0]["median"]
    assert client.get(f"{API}/metrics/hrv_rmssd").json()["band"] is None

    wd = client.get(f"{API}/metrics/steps/weekday").json()
    assert [d["weekday"] for d in wd["days"]] == list(range(7))
    assert all(d["n"] > 0 for d in wd["days"])


def test_correlate(rich, client):  # noqa: F811
    body = client.get(f"{API}/explore/correlate?a=hrv_rmssd&b=azm&from=2026-10-15").json()
    assert body["n"] == len(body["points"]) > 20
    assert body["r"] is not None and -1 <= body["r"] <= 1
    assert client.get(f"{API}/explore/correlate?a=hrv_rmssd&b=zzz").status_code == 404


def test_heatmap(client):  # noqa: F811
    body = client.get(f"{API}/activity/heatmap?from=2026-10-01").json()
    assert len(body["values"]) == 7 and all(len(r) == 24 for r in body["values"])
    # Seeded 1000 steps at 08:00, 12:00 and 18:00 local on every history day.
    for row, n in zip(body["values"], body["days"], strict=True):
        if n:
            assert row[8] is not None and row[8] > 0
            assert row[3] == 0


def test_exercises_and_detail(rich, client):  # noqa: F811
    lst = client.get(f"{API}/exercises").json()["exercises"]
    assert len(lst) == 1 and lst[0]["duration_min"] == 5 and lst[0]["distance_km"] == 1
    detail = client.get(f"{API}/exercises/{lst[0]['id']}").json()
    tiz = {z["zone"]: z["minutes"] for z in detail["time_in_zones"]}
    assert tiz == {"below": 1, "light": 1, "moderate": 1, "vigorous": 2}
    assert detail["max_hr"] == 148 and len(detail["points"]) == 5
    assert client.get(f"{API}/exercises/nope").status_code == 404


def test_records(rich, client):  # noqa: F811
    body = client.get(f"{API}/records").json()
    bests = {b["key"]: b for b in body["bests"]}
    assert bests["steps"]["value"] == 12_000
    assert bests["longest_workout"]["note"] == "Run"
    assert "resting_hr" in bests and "azm_week" in bests
    streaks = {s["key"]: s for s in body["streaks"]}
    assert streaks["steps"]["current"] == 40 and streaks["steps"]["period"] == "day"
    assert streaks["sleep"]["current"] == 0  # 420 < 480 goal
    assert streaks["azm"]["period"] == "week"


class _StubService:
    running, job, next_run = False, None, None

    def __init__(self, ok: bool) -> None:
        self.ok = ok

    def start_backfill(self, since):
        return self.ok

    def start_resync(self, streams, since, until=None):
        self.last_resync = (streams, since, until)
        return self.ok

    def next_backup(self):
        return None


def test_jobs(app_env, client):  # noqa: F811
    app = app_env[0]
    assert client.post(f"{API}/backfill", json={}).status_code == 503
    app.state.sync_service = _StubService(ok=True)
    assert client.post(f"{API}/backfill", json={"since": "2025-01-01"}).status_code == 202
    assert client.post(f"{API}/resync", json={"since": "2026-11-01"}).json()["job"] == "resync"
    bad = client.post(f"{API}/resync", json={"since": "2026-11-01", "streams": ["nope"]})
    assert bad.status_code == 422
    future = client.post(f"{API}/resync", json={"since": "2027-01-01"})
    assert future.status_code == 422
    app.state.sync_service = _StubService(ok=False)
    assert client.post(f"{API}/backfill", json={}).status_code == 409
    status = client.get(f"{API}/status").json()
    assert "sleep" in status["stream_names"]


def test_derive_is_idempotent_and_leaves_synced_rows(rich):
    _, sessions, _ = rich
    with sessions() as s:
        before = s.execute(select(DailyMetric.metric, DailyMetric.civil_date, DailyMetric.value))
        snapshot = sorted(before.all())
        n = derive.recompute(s)
        s.commit()
        assert n > 0
        after = sorted(
            s.execute(select(DailyMetric.metric, DailyMetric.civil_date, DailyMetric.value)).all()
        )
    assert after == snapshot
