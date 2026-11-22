"""Data health maths: day lengths, missing-day runs, wear gaps, freshness. Pure, no I/O."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pulse.datatypes import CivilWindow

LOW_WEAR = 0.5  # below half the day: the band was mostly off
MIN_GAP_MINUTES = 60
FRESH_MIN, BEHIND_MIN = 60, 6 * 60

Freshness = Literal["fresh", "behind", "stale", "none"]


def day_bounds(d: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    return CivilWindow(d, d + timedelta(days=1), zone).utc_bounds()


def day_minutes(d: date, zone: ZoneInfo) -> int:
    """1440, or 1380 / 1500 on DST change days."""
    lo, hi = day_bounds(d, zone)
    return round((hi - lo).total_seconds() / 60)


@dataclass(frozen=True)
class Gap:
    start: date
    end: date  # inclusive

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def gaps(present: Iterable[date], first: date | None, last: date, today: date) -> list[Gap]:
    """Runs of missing days in [first, last], never before the first day with data and never
    including today (still in progress). Oldest first."""
    if first is None:
        return []
    have = set(present)
    end = min(last, today - timedelta(days=1))
    out: list[Gap] = []
    run_start: date | None = None
    d = first
    while d <= end:
        if d not in have:
            run_start = run_start or d
        elif run_start is not None:
            out.append(Gap(run_start, d - timedelta(days=1)))
            run_start = None
        d += timedelta(days=1)
    if run_start is not None:
        out.append(Gap(run_start, end))
    return out


@dataclass(frozen=True)
class WearGap:
    start: datetime
    end: datetime

    @property
    def minutes(self) -> int:
        return round((self.end - self.start).total_seconds() / 60)


def intraday_gaps(
    minutes: Sequence[datetime],
    window: tuple[datetime, datetime],
    min_minutes: int = MIN_GAP_MINUTES,
) -> list[WearGap]:
    """Stretches of at least ``min_minutes`` with no 1-minute heart-rate sample inside a day
    window (UTC). Each sample covers [t, t + 1 min). The day's edges count, so "nothing after
    18:00" is a gap; pass ``window`` ending at "now" for today."""
    lo, hi = window
    cursor = lo
    out: list[WearGap] = []
    one = timedelta(minutes=1)
    for t in sorted(x for x in minutes if lo <= x < hi):
        if (t - cursor) >= timedelta(minutes=min_minutes):
            out.append(WearGap(cursor, t))
        cursor = max(cursor, t + one)
    if (hi - cursor) >= timedelta(minutes=min_minutes):
        out.append(WearGap(cursor, hi))
    return out


def freshness(latest: datetime | None, now: datetime) -> tuple[float | None, Freshness]:
    """(lag in minutes, status) for the newest data point of a signal."""
    if latest is None:
        return None, "none"
    lag = max(0.0, (now - latest).total_seconds() / 60)
    status: Freshness = "fresh" if lag < FRESH_MIN else "behind" if lag < BEHIND_MIN else "stale"
    return round(lag, 1), status
