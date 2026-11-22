"""What Pulse fetches, how, and which rows each stream owns.

A stream owns a set of rows per civil date; on every fetch of a window it replaces exactly
those rows (delete-in-window, then upsert), so device revisions and deletions propagate.
Method choices come from live probing (docs/COVERAGE.md): totals come from rollups because
listed points include duplicate sources (band, phone, Health Connect).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pulse.client import HealthClient
from pulse.datatypes import CivilWindow
from pulse.sync import parsers as P

JSON = dict[str, Any]


@dataclass(frozen=True)
class Clear:
    """Rows a stream owns in a table: optionally restricted to ``column`` values.
    Values ending in ``*`` are prefixes."""

    table: str
    column: str | None = None
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class FetchContext:
    client: HealthClient
    window: CivilWindow
    zone: ZoneInfo
    fetched_at: datetime


Fetcher = Callable[[FetchContext], P.Batch]


@dataclass(frozen=True)
class Stream:
    name: str
    chunk_days: int
    fetch: Fetcher
    owns: tuple[Clear, ...]
    description: str = ""


def _civil(d: date) -> JSON:
    return {"date": {"year": d.year, "month": d.month, "day": d.day}}


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _daily_rollups(types: tuple[str, ...]) -> Fetcher:
    def fetch(ctx: FetchContext) -> P.Batch:
        b = P.Batch()
        body = {
            "range": {"start": _civil(ctx.window.start), "end": _civil(ctx.window.end)},
            "windowSizeDays": 1,
        }
        for t in types:
            b.extend(P.parse_daily_rollup(t, ctx.client.daily_roll_up(t, body)))
        return b

    return fetch


def _rollup(data_type: str, window_s: int, parse: Callable[..., P.Batch]) -> Fetcher:
    def fetch(ctx: FetchContext) -> P.Batch:
        s, e = ctx.window.utc_bounds()
        body = {
            "range": {"startTime": _rfc3339(s), "endTime": _rfc3339(e)},
            "windowSize": f"{window_s}s",
            "pageSize": 10_000,
        }
        pages = ctx.client.pages(
            "POST", f"users/me/dataTypes/{data_type}/dataPoints:rollUp", json=body
        )
        return parse(pages, ctx.zone)

    return fetch


def _range_filter(field: str, lo: str, hi: str) -> str:
    return f'{field} >= "{lo}" AND {field} < "{hi}"'


def _list(
    data_type: str, field: str, *, page_size: int = 10_000, reconcile: bool = False
) -> Callable[[FetchContext], list[JSON]]:
    """Fetch all pages of a list/reconcile call filtered to the window's civil dates
    (or the UTC bounds of those dates for sample types)."""

    def fetch(ctx: FetchContext) -> list[JSON]:
        if field.endswith("physical_time"):
            s, e = (_rfc3339(x) for x in ctx.window.utc_bounds())
        else:
            s, e = ctx.window.start.isoformat(), ctx.window.end.isoformat()
        prefix = data_type.replace("-", "_")
        return list(
            ctx.client.list_points(
                data_type,
                filter=_range_filter(f"{prefix}.{field}", s, e),
                page_size=page_size,
                reconcile=reconcile,
            )
        )

    return fetch


def _daily_lists(types: tuple[str, ...]) -> Fetcher:
    def fetch(ctx: FetchContext) -> P.Batch:
        b = P.Batch()
        for t in types:
            pages = _list(t, "date", page_size=1000)(ctx)
            b.extend(P.parse_daily_list(t, pages, ctx.zone, ctx.fetched_at))
        return b

    return fetch


def _intraday_lists(ctx: FetchContext) -> P.Batch:
    b = P.Batch()
    z, at = ctx.zone, ctx.fetched_at
    today = ctx.fetched_at.astimezone(z).date()
    days = [
        ctx.window.start + timedelta(days=i)
        for i in range((ctx.window.end - ctx.window.start).days)
        if ctx.window.start + timedelta(days=i) <= today
    ]
    azm_pages = _list("active-zone-minutes", "interval.civil_start_time")(ctx)
    b.extend(P.parse_azm(azm_pages, z, at, days))
    b.extend(
        P.parse_samples(
            "oxygen-saturation",
            "spo2",
            "percentage",
            _list("oxygen-saturation", "sample_time.physical_time")(ctx),
            z,
            at,
        )
    )
    b.extend(
        P.parse_samples(
            "heart-rate-variability",
            "hrv_rmssd",
            "rootMeanSquareOfSuccessiveDifferencesMilliseconds",
            _list("heart-rate-variability", "sample_time.physical_time")(ctx),
            z,
            at,
        )
    )
    b.extend(P.parse_sedentary(_list("sedentary-period", "interval.civil_start_time")(ctx), z, at))
    b.extend(
        P.parse_exercise(_list("exercise", "interval.civil_start_time", page_size=25)(ctx), z, at)
    )
    return b


def _sleep(ctx: FetchContext) -> P.Batch:
    pages = _list("sleep", "interval.civil_end_time", page_size=25, reconcile=True)(ctx)
    return P.parse_sleep(pages, ctx.zone, ctx.fetched_at)


ROLLUP_90 = (
    "steps",
    "distance",
    "active-energy-burned",
    "sedentary-period",
    "time-in-heart-rate-zone",
)
ROLLUP_14 = ("heart-rate", "total-calories", "calories-in-heart-rate-zone", "active-minutes")
DAILY_LISTS = (
    "daily-resting-heart-rate",
    "daily-heart-rate-variability",
    "daily-oxygen-saturation",
    "daily-sleep-temperature-derivations",
    "daily-heart-rate-zones",
)

STREAMS: tuple[Stream, ...] = (
    Stream(
        "daily_rollups_90",
        90,
        _daily_rollups(ROLLUP_90),
        (
            Clear(
                "daily_metrics",
                "metric",
                ("steps", "distance_km", "calories_active", "sedentary_min", "hr_zone_min_*"),
            ),
        ),
        "Daily totals: steps, distance, active kcal, sedentary, time in HR zones",
    ),
    Stream(
        "daily_rollups_14",
        14,
        _daily_rollups(ROLLUP_14),
        (
            Clear(
                "daily_metrics",
                "metric",
                ("hr_avg", "hr_min", "hr_max", "calories_total", "hr_zone_kcal_*", "active_min_*"),
            ),
        ),
        "Daily HR summary, total kcal, kcal per HR zone, active minutes",
    ),
    Stream(
        "daily_lists",
        90,
        _daily_lists(DAILY_LISTS),
        (
            Clear("raw_points", "data_type", DAILY_LISTS),
            Clear(
                "daily_metrics",
                "metric",
                (
                    "resting_hr",
                    "hrv_rmssd",
                    "hrv_deep_rmssd",
                    "nonrem_hr",
                    "spo2_avg",
                    "spo2_low",
                    "spo2_high",
                    "skin_temp_nightly",
                    "skin_temp_baseline",
                    "skin_temp_delta",
                ),
            ),
            Clear("hr_zone_bounds"),
        ),
        "Resting HR, HRV, SpO2, skin temperature, HR zone boundaries",
    ),
    Stream(
        "hr_minute",
        7,
        _rollup("heart-rate", 60, P.parse_hr_rollup),
        (Clear("intraday_hr"),),
        "1-minute heart rate (avg/min/max)",
    ),
    Stream(
        "steps_15m",
        90,
        _rollup("steps", 900, P.parse_steps_rollup),
        (Clear("intraday_steps"),),
        "15-minute steps",
    ),
    Stream(
        "intraday_lists",
        30,
        _intraday_lists,
        (
            Clear(
                "raw_points",
                "data_type",
                (
                    "active-zone-minutes",
                    "oxygen-saturation",
                    "heart-rate-variability",
                    "sedentary-period",
                    "exercise",
                ),
            ),
            Clear("daily_metrics", "metric", ("azm", "azm_*")),
            Clear("intraday_samples", "metric", ("spo2", "hrv_rmssd")),
            Clear("exercises"),
        ),
        "AZM, SpO2 and HRV samples, sedentary periods, exercises",
    ),
    Stream(
        "sleep",
        30,
        _sleep,
        (
            Clear("raw_points", "data_type", ("sleep",)),
            Clear("sleep_sessions"),
            Clear(
                "daily_metrics",
                "metric",
                ("sleep_*", "bedtime_min", "waketime_min"),
            ),
        ),
        "Sleep sessions and stages (reconciled across sources)",
    ),
)

STREAMS_BY_NAME = {s.name: s for s in STREAMS}
