"""Recompute derived daily metrics (readiness, strain, load, sleep debt, ...) from synced data.

Runs after every sync/backfill/refill and when goals or readiness weights change. It always
recomputes all history: a couple of years of days is milliseconds of work, and a changed
value shifts the 28-day baselines of the following month anyway. Only the derived keys are
replaced; synced metrics are never touched.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, sessionmaker

from pulse import derived, prefs
from pulse.metrics import DERIVED_KEYS
from pulse.models import DailyMetric

log = logging.getLogger(__name__)

INPUTS = (
    "azm",
    "calories_total",
    "calories_active",
    "sleep_main_min",
    "bedtime_min",
    "waketime_min",
    "hrv_rmssd",
    "resting_hr",
)


def _as_date(v: object) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def load_series(session: Session, keys: tuple[str, ...] = INPUTS) -> dict[str, dict[date, float]]:
    out: dict[str, dict[date, float]] = defaultdict(dict)
    for metric, d, v in session.execute(
        select(DailyMetric.metric, DailyMetric.civil_date, DailyMetric.value).where(
            DailyMetric.metric.in_(keys)
        )
    ):
        out[metric][d] = v
    return dict(out)


def sedentary_longest(session: Session) -> dict[date, float]:
    """Longest single sedentary period per civil day, in minutes (SQL over raw intervals)."""
    rows = session.execute(
        text(
            "SELECT civil_date, MAX((julianday(end_utc) - julianday(start_utc)) * 1440.0) "
            "FROM raw_points WHERE data_type = 'sedentary-period' "
            "AND start_utc IS NOT NULL AND end_utc IS NOT NULL GROUP BY civil_date"
        )
    ).all()
    return {_as_date(d): round(float(v), 1) for d, v in rows if v is not None}


def recompute(session: Session) -> int:
    """Replace all derived rows. Caller owns the transaction (commit happens on exit)."""
    t0 = datetime.now(UTC)
    rows = derived.derive_daily(
        load_series(session),
        sleep_goal_min=prefs.goals(session)["sleep_min"],
        weights=prefs.readiness_weights(session),
        sedentary_longest=sedentary_longest(session),
    )
    session.execute(delete(DailyMetric).where(DailyMetric.metric.in_(DERIVED_KEYS)))
    session.add_all(
        DailyMetric(civil_date=d, metric=k, value=v, unit=derived.DERIVED_UNITS[k])
        for d, k, v in rows
    )
    session.flush()
    ms = (datetime.now(UTC) - t0).total_seconds() * 1000
    log.info("derived metrics recomputed: %d rows in %.0f ms", len(rows), ms)
    return len(rows)


def recompute_safely(sessions: sessionmaker[Session]) -> None:
    """Run recompute in its own transaction; never let a derive failure fail a sync."""
    try:
        with sessions() as s, s.begin():
            recompute(s)
    except Exception:
        log.exception("derived metric recompute failed")
