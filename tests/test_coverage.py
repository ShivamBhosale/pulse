"""Data health: day lengths, missing-day runs, wear gaps, freshness, API, re-sync ranges."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from pulse import coverage as C
from pulse.models import DailyMetric, IntradayHR
from tests.test_api import NOW, TODAY, app_env, client  # noqa: F401 - pytest fixtures
from tests.test_api_phase2 import _StubService

TZ = ZoneInfo("America/New_York")
API = "/api/v1"


def test_day_minutes_dst() -> None:
    assert C.day_minutes(date(2026, 11, 22), TZ) == 1440
    assert C.day_minutes(date(2026, 3, 8), TZ) == 1380  # spring forward
    assert C.day_minutes(date(2026, 11, 1), TZ) == 1500  # fall back


def _days(*offsets: int, base: date = date(2026, 11, 1)) -> set[date]:
    return {base + timedelta(days=o) for o in offsets}


def test_gaps_runs_and_edges() -> None:
    base = date(2026, 11, 1)
    today = base + timedelta(days=10)
    present = _days(0, 1, 4, 5, 6, 9)  # missing 2-3, 7-8; 10 = today
    g = C.gaps(present, base, today, today)
    assert [(x.start, x.days) for x in g] == [(base + timedelta(2), 2), (base + timedelta(7), 2)]


def test_gaps_never_before_first_or_including_today() -> None:
    base = date(2026, 11, 1)
    today = base + timedelta(days=5)
    assert C.gaps(_days(3, 4), base + timedelta(3), today, today) == []
    # Missing through yesterday: run ends at yesterday, not today.
    g = C.gaps(_days(0), base, today, today)
    assert g == [C.Gap(base + timedelta(1), base + timedelta(4))]
    assert C.gaps(set(), None, today, today) == []


def _utc(d: date, hh: int, mm: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, tzinfo=TZ).astimezone(UTC)


def test_intraday_gaps_edges_and_threshold() -> None:
    d = date(2026, 11, 20)
    window = C.day_bounds(d, TZ)
    # Worn 01:00-12:00 with a 45-minute break (not a gap) and a 2-hour break (gap).
    minutes = [_utc(d, 1) + timedelta(minutes=i) for i in range(0, 11 * 60)]
    minutes = [m for m in minutes if not (_utc(d, 4) <= m < _utc(d, 4, 45))]
    minutes = [m for m in minutes if not (_utc(d, 8) <= m < _utc(d, 10))]
    g = C.intraday_gaps(minutes, window)
    assert [(x.start, x.minutes) for x in g] == [
        (_utc(d, 0), 60),  # start of day
        (_utc(d, 8), 120),
        (_utc(d, 12), 720),  # nothing after noon
    ]


def test_intraday_gaps_dst_day_length() -> None:
    d = date(2026, 11, 1)  # 25 hours
    g = C.intraday_gaps([], C.day_bounds(d, TZ))
    assert len(g) == 1 and g[0].minutes == 1500


def test_freshness_thresholds() -> None:
    now = datetime(2026, 11, 22, 17, tzinfo=UTC)
    assert C.freshness(None, now) == (None, "none")
    assert C.freshness(now - timedelta(minutes=10), now) == (10.0, "fresh")
    assert C.freshness(now - timedelta(hours=2), now)[1] == "behind"
    assert C.freshness(now - timedelta(hours=7), now)[1] == "stale"


# ---- API -------------------------------------------------------------------------------------


def test_coverage_api(app_env, client):  # noqa: F811
    _, sessions, _ = app_env
    with sessions() as s:
        # HRV starts 10 days ago with one missing day (5 days ago).
        for i in range(1, 11):
            if i != 5:
                d = TODAY - timedelta(days=i)
                s.merge(DailyMetric(civil_date=d, metric="hrv_rmssd", value=40, unit="ms"))
        # Two days ago: band worn 6 hours only → low wear.
        d2 = TODAY - timedelta(days=2)
        start = _utc(d2, 8)
        for m in range(360):
            s.merge(
                IntradayHR(
                    ts_utc=start + timedelta(minutes=m),
                    civil_date=d2,
                    bpm_avg=70,
                    bpm_min=68,
                    bpm_max=72,
                )
            )
        s.commit()
    body = client.get(f"{API}/data-health/coverage?from={TODAY - timedelta(days=14)}").json()
    assert len(body["days"]) == 15
    sig = {x["key"]: x for x in body["signals"]}
    hrv = sig["hrv"]
    assert hrv["cells"][:4] == ["untracked"] * 4  # before HRV began
    assert hrv["cells"][-1] == "today"
    assert hrv["gaps"] == [
        {"start": str(TODAY - timedelta(days=5)), "end": str(TODAY - timedelta(days=5)), "days": 1}
    ]
    assert hrv["present_days"] == 9 and hrv["expected_days"] == 10 and hrv["current_gap"] == 0
    wear = sig["wear"]
    i2 = body["days"].index(str(TODAY - timedelta(days=2)))
    assert wear["cells"][i2] == "low" and wear["values"][i2] == 0.25
    assert sig["wear"]["stream"] == "hr_minute"
    assert client.get(f"{API}/data-health/coverage?from=2020-01-01").status_code == 422


def test_day_health_api(app_env, client):  # noqa: F811
    _, sessions, _ = app_env
    d2 = TODAY - timedelta(days=2)
    with sessions() as s:
        start = _utc(d2, 8)
        for m in range(360):
            s.merge(
                IntradayHR(
                    ts_utc=start + timedelta(minutes=m),
                    civil_date=d2,
                    bpm_avg=70,
                    bpm_min=68,
                    bpm_max=72,
                )
            )
        s.commit()
    body = client.get(f"{API}/data-health/day?date={d2}").json()
    assert body["wear_minutes"] == 360 and body["day_minutes"] == 1440
    assert [g["minutes"] for g in body["wear_gaps"]] == [480, 600]
    assert body["signals"]["wear"] == "low"
    assert client.get(f"{API}/data-health/day?date={TODAY + timedelta(days=1)}").status_code == 422


def test_freshness_api(client):  # noqa: F811
    body = client.get(f"{API}/data-health/freshness").json()
    assert body["band"]["key"] == "wear"
    assert {s["key"] for s in body["signals"]} >= {"wear", "sleep", "steps", "hrv"}
    for s in body["signals"]:
        assert s["status"] in {"fresh", "behind", "stale", "none"}
    assert body["now"].startswith(NOW.date().isoformat())


def test_resync_range_validation(app_env, client):  # noqa: F811
    app = app_env[0]
    stub = _StubService(ok=True)
    app.state.sync_service = stub
    day = str(TODAY - timedelta(days=3))
    r = client.post(f"{API}/resync", json={"since": day, "until": day, "streams": ["sleep"]})
    assert r.status_code == 202
    assert stub.last_resync == (["sleep"], TODAY - timedelta(days=3), TODAY - timedelta(days=3))
    bad = [
        {"since": day, "until": str(TODAY - timedelta(days=4))},
        {"since": day, "until": str(TODAY + timedelta(days=1))},
        {"since": "2024-01-01", "until": str(TODAY)},
    ]
    for body in bad:
        assert client.post(f"{API}/resync", json=body).status_code == 422
    app.state.sync_service = _StubService(ok=False)
    assert client.post(f"{API}/resync", json={"since": day}).status_code == 409
