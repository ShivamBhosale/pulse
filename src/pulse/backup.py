"""Backups of the SQLite database: online backup → integrity check → gzip, with rotation.

Backups hold all of your health data, so files are written 0600 inside the (git-ignored)
data directory and are never served over HTTP.
"""

from __future__ import annotations

import fcntl
import gzip
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import threading
from collections.abc import Callable, Hashable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import IO
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from pulse.fileio import PRIVATE_MODE, ensure_private_dir
from pulse.models import SyncState

log = logging.getLogger(__name__)

NAME_RE = re.compile(r"^pulse-(\d{4}-\d{2}-\d{2})-(\d{4})\.db\.gz$")
KEEP_DAILY, KEEP_WEEKLY, KEEP_MONTHLY = 7, 4, 6


class BackupError(RuntimeError):
    pass


class ServerRunning(BackupError):
    pass


@dataclass(frozen=True)
class BackupFile:
    path: Path
    taken_at: datetime  # local wall time from the file name
    size_bytes: int

    @property
    def day(self) -> date:
        return self.taken_at.date()


def list_backups(dest_dir: Path) -> list[BackupFile]:
    """Backups in ``dest_dir``, newest first (files not matching the name pattern are ignored)."""
    if not dest_dir.exists():
        return []
    out = []
    for p in dest_dir.iterdir():
        m = NAME_RE.match(p.name)
        if m and p.is_file():
            taken = datetime.strptime(f"{m[1]} {m[2]}", "%Y-%m-%d %H%M")
            out.append(BackupFile(p, taken, p.stat().st_size))
    return sorted(out, key=lambda b: b.taken_at, reverse=True)


def _integrity_ok(db: Path) -> str | None:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        result = con.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        con.close()
    return None if result == "ok" else str(result)


def create_backup(db_path: Path, dest_dir: Path, now: datetime | None = None) -> BackupFile:
    """Consistent snapshot of a live WAL database via SQLite's online backup API."""
    if not db_path.exists():
        raise BackupError(f"no database at {db_path}")
    taken = (now or datetime.now()).replace(second=0, microsecond=0)
    ensure_private_dir(dest_dir)
    target = dest_dir / f"pulse-{taken:%Y-%m-%d-%H%M}.db.gz"
    with tempfile.TemporaryDirectory(dir=dest_dir, prefix=".tmp-backup-") as tmp:
        Path(tmp).chmod(0o700)
        snap = Path(tmp) / "snapshot.db"
        src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        dst = sqlite3.connect(snap)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        snap.chmod(PRIVATE_MODE)
        problem = _integrity_ok(snap)
        if problem:
            raise BackupError(f"integrity check failed on snapshot: {problem}")
        partial = Path(tmp) / "out.gz"
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, PRIVATE_MODE)
        with (
            os.fdopen(fd, "wb") as raw,
            gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz,
            snap.open("rb") as fh,
        ):
            shutil.copyfileobj(fh, gz, length=1024 * 1024)
        partial.replace(target)  # atomic within the same directory tree
    log.info("backup written: %s (%d bytes)", target.name, target.stat().st_size)
    return BackupFile(target, taken, target.stat().st_size)


def plan_rotation(
    backups: list[BackupFile],
    today: date,
    daily: int = KEEP_DAILY,
    weekly: int = KEEP_WEEKLY,
    monthly: int = KEEP_MONTHLY,
) -> list[BackupFile]:
    """Files to delete: keep the newest backup of each of the last ``daily`` days, ``weekly``
    ISO weeks and ``monthly`` months (periods counted back from ``today``). The newest backup
    overall is always kept."""
    if not backups:
        return []
    newest_first = sorted(backups, key=lambda b: b.taken_at, reverse=True)
    keep: set[Path] = {newest_first[0].path}

    def keep_newest_per(period_of: Callable[[date], Hashable], periods: set[Hashable]) -> None:
        seen: set[Hashable] = set()
        for b in newest_first:
            key = period_of(b.day)
            if key in periods and key not in seen:
                seen.add(key)
                keep.add(b.path)

    def back(days: int) -> date:
        return date.fromordinal(today.toordinal() - days)

    def iso_week(d: date) -> Hashable:
        return d.isocalendar()[:2]

    keep_newest_per(lambda d: d, {back(i) for i in range(daily)})
    keep_newest_per(iso_week, {iso_week(back(7 * i)) for i in range(weekly)})
    months: set[Hashable] = set()
    y, m = today.year, today.month
    for _ in range(monthly):
        months.add((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    keep_newest_per(lambda d: (d.year, d.month), months)
    return [b for b in newest_first if b.path not in keep]


def rotate(dest_dir: Path, today: date) -> list[Path]:
    removed = []
    for b in plan_rotation(list_backups(dest_dir), today):
        b.path.unlink(missing_ok=True)
        removed.append(b.path)
    if removed:
        log.info("backup rotation removed %d file(s)", len(removed))
    return removed


# ---- restore ------------------------------------------------------------------------------


@contextmanager
def _try_lock(path: Path) -> Iterator[bool]:
    """Yield True if we could take the lock (nobody else holds it)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fh: IO[str] = path.open("a")
    try:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    finally:
        fh.close()


@contextmanager
def server_presence(path: Path) -> Iterator[None]:
    """Held for the lifetime of `pulse serve` so a restore can tell the server is up."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fh: IO[str] = path.open("a")
    try:
        try:
            fcntl.flock(fh, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:  # a restore is in progress; serve anyway, it will fail loudly
            log.warning("server lock busy (restore running?)")
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def restore_backup(backup: Path, db_path: Path, *, server_lock: Path, sync_lock: Path) -> Path:
    """Replace the database with ``backup``. Refuses while the server or a sync is running.
    Returns the path the previous database was moved to."""
    if not backup.exists():
        raise BackupError(f"no such backup: {backup}")
    with _try_lock(server_lock) as free_server, _try_lock(sync_lock) as free_sync:
        if not free_server:
            raise ServerRunning(
                "the Pulse server is running. Stop it first: `docker compose stop`, then run "
                "`docker compose run --rm pulse restore <file>` and `docker compose up -d`."
            )
        if not free_sync:
            raise ServerRunning("a sync or backfill is running; wait for it or stop it first")
        with tempfile.TemporaryDirectory(dir=db_path.parent, prefix=".tmp-restore-") as tmp:
            staged = Path(tmp) / "restore.db"
            opener = gzip.open if backup.suffix == ".gz" else open
            with opener(backup, "rb") as src, staged.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            staged.chmod(PRIVATE_MODE)
            problem = _integrity_ok(staged)
            if problem:
                raise BackupError(f"backup failed its integrity check: {problem}")
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            previous = db_path.with_name(f"{db_path.name}.pre-restore-{stamp}")
            if db_path.exists():
                # Fold the WAL into the old file first so the kept copy is complete.
                con = sqlite3.connect(db_path)
                try:
                    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                finally:
                    con.close()
                db_path.replace(previous)
            for suffix in ("-wal", "-shm"):
                db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
            staged.replace(db_path)
    log.info("restored %s; previous database kept at %s", backup.name, previous.name)
    return previous


# ---- runner (scheduler + API) -------------------------------------------------------------

BACKUP_ROW = "_backup"


class BackupRunner:
    """Runs one backup at a time (nightly job, API button) and records the outcome in the
    ``_backup`` row of sync_state. Reading the database while a sync writes is safe."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        db_path: Path,
        dest_dir: Path,
        zone: ZoneInfo,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.sessions, self.db_path, self.dest_dir, self.zone, self.now = (
            sessions,
            db_path,
            dest_dir,
            zone,
            now,
        )
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._lock.locked()

    def run(self) -> BackupFile | None:
        if not self._lock.acquire(blocking=False):
            return None
        try:
            return self._run()
        finally:
            self._lock.release()

    def start(self) -> bool:
        if not self._lock.acquire(blocking=False):
            return False

        def work() -> None:
            try:
                self._run()
            finally:
                self._lock.release()

        threading.Thread(target=work, name="pulse-backup", daemon=True).start()
        return True

    def _run(self) -> BackupFile | None:
        local = self.now().astimezone(self.zone)
        try:
            made = create_backup(self.db_path, self.dest_dir, local.replace(tzinfo=None))
            rotate(self.dest_dir, local.date())
        except Exception as exc:
            log.exception("backup failed")
            self._record(error=f"{type(exc).__name__}: {exc}"[:500])
            return None
        self._record(error=None)
        return made

    def _record(self, error: str | None) -> None:
        with self.sessions() as s:
            row = s.get(SyncState, BACKUP_ROW) or SyncState(stream=BACKUP_ROW)
            s.add(row)
            if error is None:
                row.last_success, row.last_error = self.now(), None
            else:
                row.last_error, row.last_error_at = error, self.now()
            s.commit()
