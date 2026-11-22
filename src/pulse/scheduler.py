"""In-process scheduler: incremental sync every N minutes, plus on-demand triggers."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session, sessionmaker

from pulse.auth import AuthError
from pulse.client import HealthClient
from pulse.sync.engine import SyncBusy, SyncEngine, SyncReport

log = logging.getLogger(__name__)
JOB_ID = "sync"


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

    @property
    def running(self) -> bool:
        return self._running.is_set()

    @property
    def next_run(self) -> datetime | None:
        if not self._scheduler:
            return None
        job = self._scheduler.get_job(JOB_ID)
        return job.next_run_time if job else None

    def start(self) -> None:
        self._scheduler = BackgroundScheduler(timezone=UTC)
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

    def run_once(self) -> SyncReport | None:
        if self._running.is_set():
            return None
        self._running.set()
        try:
            with self.client_factory() as client:
                engine = SyncEngine(self.sessions, client, self.zone, lock_path=self.lock_path)
                report = engine.run_sync()
            self.last_report = report
            log.info("sync finished ok=%s requests=%d", report.ok, report.requests)
            return report
        except SyncBusy:
            log.info("sync skipped: another sync is running")
            return None
        except AuthError as exc:  # no token at all
            log.error("sync skipped: %s", exc)
            return None
        except Exception:
            log.exception("sync crashed")
            return None
        finally:
            self._running.clear()

    def trigger(self) -> bool:
        """Start a sync in the background now. False if one is already running."""
        if self._running.is_set():
            return False
        threading.Thread(target=self.run_once, name="pulse-sync-manual", daemon=True).start()
        return True
