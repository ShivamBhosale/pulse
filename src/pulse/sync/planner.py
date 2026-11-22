"""Pure window/chunk planning for sync and backfill."""

from __future__ import annotations

from datetime import date, timedelta

LOOKBACK_DAYS = 3  # the device revises recent data; always re-fetch this many days


def sync_window(high_water_mark: date | None, today: date) -> tuple[date, date]:
    """Half-open civil-date window [start, end) for an incremental run."""
    anchor = min(high_water_mark or today, today)
    return anchor - timedelta(days=LOOKBACK_DAYS), today + timedelta(days=1)


def chunks(
    start: date, end: date, max_days: int, *, newest_first: bool = False
) -> list[tuple[date, date]]:
    """Split [start, end) into consecutive pieces of at most ``max_days`` days."""
    if max_days < 1:
        raise ValueError("max_days must be >= 1")
    out: list[tuple[date, date]] = []
    if newest_first:
        hi = end
        while hi > start:
            lo = max(start, hi - timedelta(days=max_days))
            out.append((lo, hi))
            hi = lo
    else:
        lo = start
        while lo < end:
            hi = min(end, lo + timedelta(days=max_days))
            out.append((lo, hi))
            lo = hi
    return out
