import json
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from pulse.auth import AuthError
from pulse.db import make_engine, make_session_factory, migrate
from pulse.models import DailyMetric, IntradayHR, SleepSession, SleepStage, SyncState
from pulse.sync.engine import AUTH_ROW, BACKFILL_ROW, SyncBusy, SyncEngine, sync_lock
from tests.fakeapi import FakeApi

TZ = ZoneInfo("America/Toronto")
TODAY = date(2026, 11, 21)
NOW = datetime(2026, 11, 21, 17, 0, tzinfo=UTC)  # noon in Toronto


def at(d: date, hour: int, minute: int = 0) -> datetime:
    """UTC instant for a Toronto wall-clock time in November (EST, UTC-5)."""
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=UTC) + timedelta(hours=5)


@pytest.fixture
def db():
    engine = make_engine(None)
    migrate(engine)
    return make_session_factory(engine)


@pytest.fixture
def api():
    fake = FakeApi()
    for i in range(6):
        d = TODAY - timedelta(days=i)
        fake.steps[d] = 1000 * (i + 1)
        fake.resting_hr[d] = 60 + i
        fake.hr[at(d, 9, 0)] = 70.0 + i
        fake.hr[at(d, 9, 1)] = 72.0 + i
        fake.sleep[f"s{i}"] = (at(d - timedelta(days=1), 23, 0), at(d, 7, 0))
    return fake


def engine_for(db, api, **kw) -> SyncEngine:
    return SyncEngine(db, kw.pop("client", None) or api.client(), TZ, now=lambda: NOW, **kw)


def counts(db) -> dict[str, int]:
    with db() as s:
        return {
            m.__tablename__: s.execute(select(func.count()).select_from(m)).scalar_one()
            for m in (DailyMetric, IntradayHR, SleepSession, SleepStage)
        }


def metric(db, name: str, d: date) -> float | None:
    with db() as s:
        row = s.get(DailyMetric, (d, name))
        return row.value if row else None


def test_sync_fetches_rolling_window_only(db, api):
    report = engine_for(db, api).run_sync()
    assert report.ok, report
    window = [TODAY - timedelta(days=i) for i in range(4)]  # today + 3 days back
    assert [metric(db, "steps", d) for d in window] == [1000, 2000, 3000, 4000]
    assert metric(db, "steps", TODAY - timedelta(days=4)) is None
    assert metric(db, "resting_hr", TODAY) == 60
    with db() as s:
        assert s.execute(select(func.count()).select_from(SleepSession)).scalar_one() == 4
        state = s.get(SyncState, "daily_rollups_90")
        assert state is not None and state.high_water_mark == TODAY
        assert s.get(SyncState, AUTH_ROW).last_error is None


def test_resync_is_idempotent(db, api):
    eng = engine_for(db, api)
    eng.run_sync()
    first = counts(db)
    eng.run_sync()
    assert counts(db) == first


def test_revisions_and_deletions_in_window_propagate(db, api):
    eng = engine_for(db, api)
    eng.run_sync()
    api.steps[TODAY - timedelta(days=1)] = 9999  # device revised yesterday
    del api.sleep["s2"]  # a session was deleted upstream
    del api.resting_hr[TODAY]
    eng.run_sync()
    assert metric(db, "steps", TODAY - timedelta(days=1)) == 9999
    assert metric(db, "resting_hr", TODAY) is None
    assert metric(db, "sleep_min", TODAY - timedelta(days=2)) is None
    with db() as s:
        ids = set(s.scalars(select(SleepSession.id)))
        assert not any(i.endswith("/s2") for i in ids)
        orphans = s.execute(
            select(func.count()).select_from(SleepStage).where(SleepStage.session_id.not_in(ids))
        ).scalar_one()
        assert orphans == 0


def test_rows_outside_window_are_left_alone(db, api):
    old = TODAY - timedelta(days=30)
    with db() as s:
        s.add(DailyMetric(civil_date=old, metric="steps", value=4242, unit="count"))
        s.commit()
    engine_for(db, api).run_sync()
    assert metric(db, "steps", old) == 4242


def test_stream_failure_is_isolated(db, api):
    api.fail_types = {"daily-resting-heart-rate"}
    report = engine_for(db, api).run_sync()
    failed = {r.stream for r in report.results if not r.ok}
    assert failed == {"daily_lists"}
    assert metric(db, "steps", TODAY) == 1000
    with db() as s:
        st = s.get(SyncState, "daily_lists")
        assert st.last_error and "INVALID_ARGUMENT" in st.last_error
        assert st.high_water_mark is None


def test_auth_failure_is_recorded_and_aborts(db, api):
    def bad_token(_force: bool) -> str:
        raise AuthError("Token refresh failed: run `pulse auth`.")

    report = engine_for(db, api, client=api.client(bad_token)).run_sync()
    assert not report.auth_ok and report.results == []
    with db() as s:
        row = s.get(SyncState, AUTH_ROW)
        assert row.last_error and "pulse auth" in row.last_error


def test_discover_earliest(db, api):
    api.steps = {TODAY - timedelta(days=150): 10, TODAY: 5, TODAY - timedelta(days=151): 0}
    assert engine_for(db, api).discover_earliest() == TODAY - timedelta(days=150)
    api.steps = {}
    assert engine_for(db, api).discover_earliest() is None


def test_backfill_is_resumable(db, api):
    floor = TODAY - timedelta(days=200)
    api.steps = {floor + timedelta(days=i): 100 + i for i in range(201)}
    eng = engine_for(db, api)
    calls = 0

    def interrupt_in_second_chunk(stream: str, lo: date, hi: date) -> None:
        nonlocal calls
        calls += 1
        if hi <= TODAY - timedelta(days=88) and stream == "daily_rollups_90":
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        eng.run_backfill(floor, progress=interrupt_in_second_chunk)
    with db() as s:
        cursor = s.get(SyncState, BACKFILL_ROW).backfill_cursor
    assert floor < cursor < TODAY  # first 90-day chunk committed
    api.calls.clear()
    report = eng.run_backfill(floor)
    assert report.ok
    fetched = [json.loads(c[2]) for c in api.calls if c[0] == "steps" and c[1] == "dailyRollUp"]
    ends = [date(**r["range"]["end"]["date"]) for r in fetched]
    assert ends and max(ends) <= cursor  # resumed below the committed chunk, no re-fetch
    with db() as s:
        n = s.execute(
            select(func.count()).select_from(DailyMetric).where(DailyMetric.metric == "steps")
        ).scalar_one()
    assert n == 201
    # Already complete: nothing left to do.
    assert eng.backfill_plan(floor) == (floor, floor)


def test_lock_prevents_overlap(db, api, tmp_path):
    lock = tmp_path / "sync.lock"
    with sync_lock(lock), pytest.raises(SyncBusy):
        engine_for(db, api, lock_path=lock).run_sync()
    assert engine_for(db, api, lock_path=lock).run_sync().ok


def test_refill_selected_stream_without_moving_cursor(db, api):
    eng = engine_for(db, api)
    report = eng.refill(["daily_rollups_90"], TODAY - timedelta(days=5))
    assert report.ok and [r.stream for r in report.results] == ["daily_rollups_90"]
    assert metric(db, "steps", TODAY - timedelta(days=5)) == 6000
    assert metric(db, "resting_hr", TODAY) is None  # other streams untouched
    with db() as s:
        assert s.get(SyncState, BACKFILL_ROW) is None
