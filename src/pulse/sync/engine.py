"""Run incremental syncs and backfills; keep sync_state honest."""

from __future__ import annotations

import fcntl
import logging
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import IO
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session, sessionmaker

from pulse import derive
from pulse.auth import AuthError
from pulse.client import HealthApiError, HealthClient, Unauthorized
from pulse.datatypes import CivilWindow
from pulse.models import SyncState
from pulse.sync.planner import chunks, sync_window
from pulse.sync.streams import STREAMS, FetchContext, Stream
from pulse.sync.writer import write_window

log = logging.getLogger(__name__)

AUTH_ROW = "_auth"
BACKFILL_ROW = "_backfill"
BACKFILL_CHUNK_DAYS = 90
DISCOVERY_CHUNK_DAYS = 90
DISCOVERY_MAX_YEARS = 15


class SyncBusy(RuntimeError):
    """Another sync/backfill holds the lock."""


@contextmanager
def sync_lock(path: Path | None) -> Iterator[None]:
    if path is None:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fh: IO[str] = path.open("a")
    try:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SyncBusy("a sync or backfill is already running") from exc
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


@dataclass
class StreamResult:
    stream: str
    ok: bool
    rows: int = 0
    error: str | None = None


@dataclass
class SyncReport:
    started_at: datetime
    finished_at: datetime | None = None
    auth_ok: bool = True
    auth_error: str | None = None
    results: list[StreamResult] = field(default_factory=list)
    requests: int = 0

    @property
    def ok(self) -> bool:
        return self.auth_ok and all(r.ok for r in self.results)


ProgressFn = Callable[[str, date, date], None]


class SyncEngine:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        client: HealthClient,
        zone: ZoneInfo,
        *,
        lock_path: Path | None = None,
        streams: tuple[Stream, ...] = STREAMS,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.sessions = sessions
        self.client = client
        self.zone = zone
        self.lock_path = lock_path
        self.streams = streams
        self.now = now

    # ---- helpers --------------------------------------------------------------------

    def today(self) -> date:
        return self.now().astimezone(self.zone).date()

    @staticmethod
    def _state(session: Session, name: str) -> SyncState:
        row = session.get(SyncState, name)
        if row is None:
            row = SyncState(stream=name)
            session.add(row)
        return row

    def _record_auth(self, ok: bool, error: str | None = None) -> None:
        with self.sessions() as s:
            st = self._state(s, AUTH_ROW)
            if ok:
                st.last_success, st.last_error = self.now(), None
            else:
                st.last_error, st.last_error_at = error, self.now()
            s.commit()

    def _fetch_write(self, stream: Stream, start: date, end: date) -> int:
        ctx = FetchContext(self.client, CivilWindow(start, end, self.zone), self.zone, self.now())
        batch = stream.fetch(ctx)
        with self.sessions() as s, s.begin():
            return write_window(s, stream, start, end, batch)

    # ---- incremental sync -------------------------------------------------------------

    def run_sync(self, only: list[str] | None = None) -> SyncReport:
        report = SyncReport(started_at=self.now())
        start_requests = self.client.request_count
        with sync_lock(self.lock_path):
            today = self.today()
            for stream in self.streams:
                if only and stream.name not in only:
                    continue
                with self.sessions() as s:
                    hwm = self._state(s, stream.name).high_water_mark
                    s.rollback()
                start, end = sync_window(hwm, today)
                try:
                    rows = 0
                    for lo, hi in chunks(start, end, stream.chunk_days):
                        rows += self._fetch_write(stream, lo, hi)
                except (AuthError, Unauthorized) as exc:
                    msg = str(exc) if isinstance(exc, AuthError) else "Google rejected the token"
                    report.auth_ok, report.auth_error = False, msg
                    self._record_auth(False, msg)
                    log.error("sync aborted: auth failure")
                    break
                except HealthApiError as exc:
                    err = f"{exc.status} {exc.code}: {exc.message}"[:500]
                    report.results.append(StreamResult(stream.name, False, error=err))
                    with self.sessions() as s:
                        st = self._state(s, stream.name)
                        st.last_error, st.last_error_at = err, self.now()
                        s.commit()
                    log.warning("stream %s failed: %s", stream.name, err)
                    continue
                report.results.append(StreamResult(stream.name, True, rows=rows))
                with self.sessions() as s:
                    st = self._state(s, stream.name)
                    st.high_water_mark = today
                    st.last_success, st.last_error = self.now(), None
                    s.commit()
                log.info("stream %s ok: %d rows [%s, %s)", stream.name, rows, start, end)
            if report.auth_ok:
                self._record_auth(True)
            if any(r.ok for r in report.results):
                derive.recompute_safely(self.sessions)
        report.finished_at = self.now()
        report.requests = self.client.request_count - start_requests
        return report

    # ---- backfill ---------------------------------------------------------------------

    def discover_earliest(self) -> date | None:
        """Walk back in 90-day dailyRollUp(steps) windows to find the first day with data."""
        hi = self.today() + timedelta(days=1)
        earliest: date | None = None
        empty_streak = 0
        limit = hi - timedelta(days=365 * DISCOVERY_MAX_YEARS)
        while hi > limit and empty_streak < 2:
            lo = hi - timedelta(days=DISCOVERY_CHUNK_DAYS)
            body = {
                "range": {
                    "start": {"date": {"year": lo.year, "month": lo.month, "day": lo.day}},
                    "end": {"date": {"year": hi.year, "month": hi.month, "day": hi.day}},
                },
                "windowSizeDays": 1,
            }
            days = [
                date(**p["civilStartTime"]["date"])
                for page in self.client.daily_roll_up("steps", body)
                for p in page.get("rollupDataPoints", []) or []
                if float((p.get("steps") or {}).get("countSum") or 0) > 0
            ]
            if days:
                earliest, empty_streak = min(days), 0
            else:
                empty_streak += 1
            hi = lo
        return earliest

    def backfill_plan(self, since: date | None, restart: bool = False) -> tuple[date, date] | None:
        """Return the [floor, cursor) range still to backfill, persisting the floor."""
        floor = since or self.discover_earliest()
        if floor is None:
            return None
        with self.sessions() as s:
            st = self._state(s, BACKFILL_ROW)
            if restart or st.backfill_floor != floor or st.backfill_cursor is None:
                st.backfill_floor = floor
                st.backfill_cursor = self.today() + timedelta(days=1)
            cursor = st.backfill_cursor
            s.commit()
        return (floor, cursor) if cursor > floor else (floor, floor)

    def refill(
        self,
        streams: list[str],
        since: date,
        until: date | None = None,
        *,
        progress: ProgressFn | None = None,
    ) -> SyncReport:
        """Re-fetch [since, until) for selected streams only. Doesn't touch the backfill
        cursor; use it to repair a range one stream failed on."""
        report = SyncReport(started_at=self.now())
        start_requests = self.client.request_count
        end = until or self.today() + timedelta(days=1)
        selected = [st for st in self.streams if st.name in streams]
        with sync_lock(self.lock_path):
            for stream in selected:
                rows, err = 0, None
                for lo, hi in chunks(since, end, stream.chunk_days, newest_first=True):
                    if progress:
                        progress(stream.name, lo, hi)
                    try:
                        rows += self._fetch_write(stream, lo, hi)
                    except (AuthError, Unauthorized) as exc:
                        report.auth_ok, report.auth_error = False, str(exc)
                        self._record_auth(False, str(exc))
                        report.finished_at = self.now()
                        return report
                    except HealthApiError as exc:
                        err = f"{exc.status} {exc.code}: {exc.message}"[:500]
                report.results.append(StreamResult(stream.name, err is None, rows, err))
            derive.recompute_safely(self.sessions)
        report.finished_at = self.now()
        report.requests = self.client.request_count - start_requests
        return report

    def run_backfill(
        self,
        since: date | None = None,
        *,
        restart: bool = False,
        progress: ProgressFn | None = None,
    ) -> SyncReport:
        """Fetch history newest-first in 90-day chunks; resumable via the _backfill row."""
        report = SyncReport(started_at=self.now())
        start_requests = self.client.request_count
        with sync_lock(self.lock_path):
            plan = self.backfill_plan(since, restart)
            if plan is None or plan[0] >= plan[1]:
                report.finished_at = self.now()
                return report
            floor, cursor = plan
            log.info("backfill start [%s, %s)", floor, cursor)
            failures: dict[str, str] = {}
            for lo, hi in chunks(floor, cursor, BACKFILL_CHUNK_DAYS, newest_first=True):
                for stream in self.streams:
                    for slo, shi in chunks(lo, hi, stream.chunk_days, newest_first=True):
                        if progress:
                            progress(stream.name, slo, shi)
                        try:
                            self._fetch_write(stream, slo, shi)
                        except (AuthError, Unauthorized) as exc:
                            report.auth_ok, report.auth_error = False, str(exc)
                            self._record_auth(False, str(exc))
                            report.finished_at = self.now()
                            return report
                        except HealthApiError as exc:
                            failures[stream.name] = f"{exc.status} {exc.code}: {exc.message}"[:500]
                            log.warning(
                                "backfill %s [%s,%s) failed: %s", stream.name, slo, shi, exc
                            )
                with self.sessions() as s:
                    self._state(s, BACKFILL_ROW).backfill_cursor = lo
                    s.commit()
                log.info("backfill chunk done [%s, %s); cursor=%s", lo, hi, lo)
            for stream in self.streams:
                err = failures.get(stream.name)
                report.results.append(StreamResult(stream.name, err is None, error=err))
            with self.sessions() as s:
                st = self._state(s, BACKFILL_ROW)
                st.last_success = self.now()
                st.last_error = "; ".join(f"{k}: {v}" for k, v in failures.items()) or None
                s.commit()
            log.info("backfill finished; failures=%s", sorted(failures) or "none")
            derive.recompute_safely(self.sessions)
        report.finished_at = self.now()
        report.requests = self.client.request_count - start_requests
        return report
