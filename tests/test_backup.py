"""Backups: online snapshot of a live WAL database, rotation, restore, scheduler and API."""

from __future__ import annotations

import fcntl
import gzip
import sqlite3
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pulse import backup as B
from pulse.api.app import create_app
from pulse.config import Settings
from pulse.db import make_engine, make_session_factory, migrate
from pulse.fileio import is_private
from pulse.models import SyncState
from pulse.scheduler import BACKUP_JOB_ID, SyncService

TZ = ZoneInfo("America/Toronto")


def _live_db(path: Path) -> sqlite3.Connection:
    """A WAL database with an open writer that has uncheckpointed rows."""
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    con.executemany("INSERT INTO t (v) VALUES (?)", [(f"row{i}",) for i in range(500)])
    con.commit()
    return con


def _rows(path: Path) -> int:
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        con.close()


def test_backup_of_live_wal_db_is_private_and_valid(tmp_path):
    db = tmp_path / "pulse.db"
    writer = _live_db(db)
    try:
        made = B.create_backup(db, tmp_path / "backups", datetime(2026, 11, 22, 3, 30))
    finally:
        writer.close()
    assert made.path.name == "pulse-2026-11-22-0330.db.gz"
    assert is_private(made.path)
    assert (tmp_path / "backups").stat().st_mode & 0o077 == 0
    restored = tmp_path / "check.db"
    restored.write_bytes(gzip.decompress(made.path.read_bytes()))
    assert _rows(restored) == 500
    assert not list((tmp_path / "backups").glob(".tmp-*"))  # temp dir cleaned up
    assert [b.path for b in B.list_backups(tmp_path / "backups")] == [made.path]


def test_backup_missing_db(tmp_path):
    with pytest.raises(B.BackupError):
        B.create_backup(tmp_path / "nope.db", tmp_path / "backups")


def _fake(day: date, hour: int = 3) -> B.BackupFile:
    taken = datetime(day.year, day.month, day.day, hour, 30)
    return B.BackupFile(Path(f"pulse-{taken:%Y-%m-%d-%H%M}.db.gz"), taken, 1)


def test_rotation_keeps_daily_weekly_monthly():
    today = date(2026, 11, 22)  # a Sunday
    files = [_fake(today - timedelta(days=i)) for i in range(400)]
    files.append(_fake(today, hour=14))  # two backups today: keep only the newest
    delete = {b.path for b in B.plan_rotation(files, today)}
    kept = sorted((b for b in files if b.path not in delete), key=lambda b: b.taken_at)
    kept_days = [b.taken_at for b in kept]
    # 7 newest days (today's newest only) …
    assert datetime(2026, 11, 22, 14, 30) in kept_days
    assert datetime(2026, 11, 22, 3, 30) not in kept_days
    for i in range(1, 7):
        assert (
            datetime.combine(today - timedelta(days=i), datetime.min.time()).replace(
                hour=3, minute=30
            )
            in kept_days
        )
    # … newest of each of the last 4 ISO weeks and last 6 months
    assert datetime(2026, 11, 8, 3, 30) in kept_days  # Sunday ending ISO week 45
    assert datetime(2026, 6, 30, 3, 30) in kept_days  # last day of June
    assert datetime(2026, 5, 31, 3, 30) not in kept_days  # 7th month back: dropped
    assert len(kept) <= 7 + 4 + 6


def test_rotation_never_deletes_newest_even_if_old():
    old = _fake(date(2020, 1, 1))
    assert B.plan_rotation([old], date(2026, 11, 22)) == []


def test_restore_round_trip(tmp_path):
    db = tmp_path / "pulse.db"
    _live_db(db).close()
    made = B.create_backup(db, tmp_path / "backups", datetime(2026, 11, 22, 3, 30))
    con = sqlite3.connect(db)
    con.execute("DELETE FROM t WHERE id > 10")
    con.commit()
    con.close()
    assert _rows(db) == 10
    previous = B.restore_backup(
        made.path, db, server_lock=tmp_path / "server.lock", sync_lock=tmp_path / "sync.lock"
    )
    assert _rows(db) == 500
    assert _rows(previous) == 10
    assert not (tmp_path / "pulse.db-wal").exists()


@pytest.mark.parametrize("held", ["server.lock", "sync.lock"])
def test_restore_refuses_while_server_or_sync_running(tmp_path, held):
    db = tmp_path / "pulse.db"
    _live_db(db).close()
    made = B.create_backup(db, tmp_path / "backups")
    with (tmp_path / held).open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_SH | fcntl.LOCK_NB)
        with pytest.raises(B.ServerRunning):
            B.restore_backup(
                made.path,
                db,
                server_lock=tmp_path / "server.lock",
                sync_lock=tmp_path / "sync.lock",
            )
    assert _rows(db) == 500


def test_restore_rejects_corrupt_backup(tmp_path):
    db = tmp_path / "pulse.db"
    _live_db(db).close()
    bad = tmp_path / "pulse-2026-11-22-0330.db.gz"
    bad.write_bytes(gzip.compress(b"not a database" * 100))
    with pytest.raises(sqlite3.DatabaseError):
        B.restore_backup(
            bad, db, server_lock=tmp_path / "server.lock", sync_lock=tmp_path / "sync.lock"
        )
    assert _rows(db) == 500  # untouched


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        static_dir=tmp_path / "dist",
        scheduler_enabled=False,
        _env_file=None,
    )  # type: ignore[call-arg]


def test_runner_records_success_and_rotation(tmp_path):
    settings = _settings(tmp_path)
    settings.data_dir.mkdir()
    engine = make_engine(settings.db_path)
    migrate(engine)
    sessions = make_session_factory(engine)
    now = datetime(2026, 11, 22, 8, 30, tzinfo=UTC)
    runner = B.BackupRunner(sessions, settings.db_path, settings.backups_path, TZ, now=lambda: now)
    made = runner.run()
    assert made is not None and made.path.name == "pulse-2026-11-22-0330.db.gz"  # local time
    with sessions() as s:
        row = s.get(SyncState, B.BACKUP_ROW)
        assert row is not None and row.last_success is not None and row.last_error is None


def test_runner_records_failure(tmp_path):
    settings = _settings(tmp_path)
    settings.data_dir.mkdir()
    engine = make_engine(None)
    migrate(engine)
    sessions = make_session_factory(engine)
    runner = B.BackupRunner(sessions, tmp_path / "missing.db", settings.backups_path, TZ)
    assert runner.run() is None
    with sessions() as s:
        row = s.get(SyncState, B.BACKUP_ROW)
        assert row is not None and "no database" in (row.last_error or "")


def test_scheduler_registers_nightly_backup(tmp_path):
    engine = make_engine(None)
    migrate(engine)
    sessions = make_session_factory(engine)
    runner = B.BackupRunner(sessions, tmp_path / "x.db", tmp_path / "b", TZ)
    svc = SyncService(sessions, lambda: None, TZ, None)  # type: ignore[arg-type,return-value]
    svc.start(runner, "03:30")
    try:
        nxt = svc.next_backup()
        assert nxt is not None
        local = nxt.astimezone(TZ)
        assert (local.hour, local.minute) == (3, 30)
        assert svc._scheduler is not None and svc._scheduler.get_job(BACKUP_JOB_ID)
    finally:
        svc.shutdown()


def test_backup_api_and_status(tmp_path):
    settings = _settings(tmp_path)
    settings.data_dir.mkdir()
    engine = make_engine(settings.db_path)
    app = create_app(settings, engine=engine, start_scheduler=False)
    with TestClient(app) as c:
        before = c.get("/api/v1/status").json()["backup"]
        assert before["count"] == 0 and before["schedule"] == "03:30" and before["enabled"]
        assert c.post("/api/v1/backup").status_code == 202
        for _ in range(100):  # background thread
            st = c.get("/api/v1/status").json()["backup"]
            if st["count"] == 1 and not st["running"]:
                break
            time.sleep(0.05)
        assert st["count"] == 1 and st["latest_file"].endswith(".db.gz")
        assert st["last_at"] is not None and st["total_bytes"] > 0
        # busy → 409
        assert app.state.backup._lock.acquire()
        try:
            assert c.post("/api/v1/backup").status_code == 409
        finally:
            app.state.backup._lock.release()
        # backups are never served over HTTP
        assert c.get(f"/backups/{st['latest_file']}").status_code == 404
        assert c.get(f"/data/backups/{st['latest_file']}").status_code == 404
