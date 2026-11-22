"""In-process scheduler: incremental sync every N minutes, plus on-demand triggers."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session, sessionmaker

from pulse.auth import AuthError
from pulse.backup import BackupRunner
from pulse.client import HealthClient
from pulse.sync.engine import SyncBusy, SyncEngine, SyncReport

log = logging.getLogger(__name__)
JOB_ID = "sync"
BACKUP_JOB_ID = "backup"


class SyncService:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        client_factory: Callable[[], HealthClient],
        zone: ZoneInfo,
        lock_path: Path | None,
        interval_min: int = 15,
    ) -> None:
        self.sessions = sessions
        self.client_factory = client_factory
        self.zone = zone
        self.lock_path = lock_path
        self.interval_min = interval_min
        self._scheduler: BackgroundScheduler | None = None
        self._running = threading.Event()
        self.last_report: SyncReport | None = None
        self.job: str | None = None
        self._guard = threading.Lock()

    @property
    def running(self) -> bool:
        return self._running.is_set()

    def next_backup(self) -> datetime | None:
        job = self._scheduler.get_job(BACKUP_JOB_ID) if self._scheduler else None
        return job.next_run_time if job else None

    @property
    def next_run(self) -> datetime | None:
        if not self._scheduler:
            return None
        job = self._scheduler.get_job(JOB_ID)
        return job.next_run_time if job else None

    def start(self, backup: BackupRunner | None = None, backup_time: str = "03:30") -> None:
        self._scheduler = BackgroundScheduler(timezone=UTC)
        if backup is not None:
            hour, minute = (int(x) for x in backup_time.split(":"))
            self._scheduler.add_job(
                backup.run,
                CronTrigger(hour=hour, minute=minute, timezone=self.zone),
                id=BACKUP_JOB_ID,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=3600,
            )
        self._scheduler.add_job(
            self.run_once,
            "interval",
            minutes=self.interval_min,
            id=JOB_ID,
            next_run_time=datetime.now(UTC) + timedelta(seconds=20),
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
        self._scheduler.start()
        log.info("scheduler started: every %d min", self.interval_min)

    def shutdown(self) -> None:
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

    def _claim(self, job: str) -> bool:
        """At most one job (sync, backfill or resync) at a time in this process; the file
        lock keeps it exclusive with CLI runs too."""
        with self._guard:
            if self._running.is_set():
                return False
            self._running.set()
            self.job = job
            return True

    def _run(self, job: str, work: Callable[[SyncEngine], SyncReport]) -> SyncReport | None:
        if not self._claim(job):
            return None
        return self._execute(job, work)

    def _execute(self, job: str, work: Callable[[SyncEngine], SyncReport]) -> SyncReport | None:
        try:
            with self.client_factory() as client:
                engine = SyncEngine(self.sessions, client, self.zone, lock_path=self.lock_path)
                report = work(engine)
            self.last_report = report
            log.info("%s finished ok=%s requests=%d", job, report.ok, report.requests)
            return report
        except SyncBusy:
            log.info("%s skipped: another sync is running", job)
            return None
        except AuthError as exc:  # no token at all
            log.error("%s skipped: %s", job, exc)
            return None
        except Exception:
            log.exception("%s crashed", job)
            return None
        finally:
            self.job = None
            self._running.clear()

    def run_once(self) -> SyncReport | None:
        return self._run("sync", lambda e: e.run_sync())

    def _start(self, job: str, work: Callable[[SyncEngine], SyncReport]) -> bool:
        if not self._claim(job):
            return False
        threading.Thread(
            target=self._execute, args=(job, work), name=f"pulse-{job}", daemon=True
        ).start()
        return True

    def trigger(self) -> bool:
        """Start a sync in the background now. False if a job is already running."""
        return self._start("sync", lambda e: e.run_sync())

    def start_backfill(self, since: date | None) -> bool:
        return self._start("backfill", lambda e: e.run_backfill(since))

    def start_resync(self, streams: list[str], since: date) -> bool:
        return self._start("resync", lambda e: e.refill(streams, since))
