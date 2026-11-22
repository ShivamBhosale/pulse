"""Registry of the Google Health data types Pulse cares about, plus filter construction.

Filter syntax follows the v4 docs (AIP-160): the data type is snake_case inside filters
and kebab-case in URLs; interval types filter on ``interval.civil_start_time``, sample types on
``sample_time.physical_time``, daily types on ``date`` and sleep on ``interval.civil_end_time``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo


class Kind(StrEnum):
    INTERVAL = "interval"
    SAMPLE = "sample"
    DAILY = "daily"
    SESSION = "session"  # exercise
    SLEEP = "sleep"


@dataclass(frozen=True)
class DataType:
    name: str  # kebab-case, as in URLs
    kind: Kind
    scope: str  # short scope name

    @property
    def snake(self) -> str:
        return self.name.replace("-", "_")

    @property
    def camel(self) -> str:
        head, *rest = self.name.split("-")
        return head + "".join(p[:1].upper() + p[1:] for p in rest)

    @property
    def value_field(self) -> str:
        """JSON union field carrying the value inside a DataPoint."""
        return self.camel

    @property
    def uses_reconcile(self) -> bool:
        return self.kind is Kind.SLEEP


_A, _H, _S = "activity_and_fitness", "health_metrics_and_measurements", "sleep"

REGISTRY: dict[str, DataType] = {
    dt.name: dt
    for dt in (
        DataType("steps", Kind.INTERVAL, _A),
        DataType("heart-rate", Kind.SAMPLE, _H),
        DataType("daily-resting-heart-rate", Kind.DAILY, _H),
        DataType("sleep", Kind.SLEEP, _S),
        DataType("daily-heart-rate-variability", Kind.DAILY, _H),
        DataType("heart-rate-variability", Kind.SAMPLE, _H),
        DataType("active-zone-minutes", Kind.INTERVAL, _A),
        DataType("total-calories", Kind.INTERVAL, _A),
        DataType("active-energy-burned", Kind.INTERVAL, _A),
        DataType("basal-energy-burned", Kind.INTERVAL, _A),
        DataType("calories-in-heart-rate-zone", Kind.INTERVAL, _A),
        DataType("daily-oxygen-saturation", Kind.DAILY, _H),
        DataType("oxygen-saturation", Kind.SAMPLE, _H),
        DataType("daily-sleep-temperature-derivations", Kind.DAILY, _H),
        DataType("distance", Kind.INTERVAL, _A),
        DataType("floors", Kind.INTERVAL, _A),
        DataType("altitude", Kind.INTERVAL, _A),
        DataType("exercise", Kind.SESSION, _A),
        DataType("sedentary-period", Kind.INTERVAL, _A),
        DataType("activity-level", Kind.INTERVAL, _A),
        DataType("vo2-max", Kind.SAMPLE, _A),
        DataType("run-vo2-max", Kind.SAMPLE, _H),
        DataType("weight", Kind.SAMPLE, _H),
        DataType("body-fat", Kind.SAMPLE, _H),
    )
}

# Page sizes from the list reference: sleep and exercise cap at 25, others at 10000.
SMALL_PAGE_KINDS = {Kind.SLEEP, Kind.SESSION}


def page_size_for(dt: DataType) -> int:
    return 25 if dt.kind in SMALL_PAGE_KINDS else 10_000


@dataclass(frozen=True)
class CivilWindow:
    """Half-open civil-date window [start, end) in a specific time zone."""

    start: date
    end: date
    zone: ZoneInfo

    @classmethod
    def last_days(cls, days: int, zone: ZoneInfo, today: date | None = None) -> CivilWindow:
        today = today or datetime.now(zone).date()
        end = today + timedelta(days=1)
        return cls(end - timedelta(days=days), end, zone)

    def utc_bounds(self) -> tuple[datetime, datetime]:
        """Local midnights converted to UTC; DST-correct because ZoneInfo resolves each date."""
        s = datetime.combine(self.start, time(0), self.zone).astimezone(UTC)
        e = datetime.combine(self.end, time(0), self.zone).astimezone(UTC)
        return s, e


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _range(field: str, lo: str, hi: str) -> str:
    return f'{field} >= "{lo}" AND {field} < "{hi}"'


def filter_for(kind: Kind, prefix: str, window: CivilWindow) -> list[str]:
    """Candidate filters for a kind, most-likely first."""
    s, e = window.start.isoformat(), window.end.isoformat()
    us, ue = (_rfc3339(x) for x in window.utc_bounds())
    match kind:
        case Kind.INTERVAL | Kind.SESSION:
            return [
                _range(f"{prefix}.interval.civil_start_time", s, e),
                _range(f"{prefix}.interval.start_time", us, ue),
            ]
        case Kind.SAMPLE:
            return [
                _range(f"{prefix}.sample_time.physical_time", us, ue),
                _range(f"{prefix}.sample_time.civil_time", s, e),
            ]
        case Kind.DAILY:
            return [_range(f"{prefix}.date", s, e)]
        case Kind.SLEEP:
            return [
                _range(f"{prefix}.interval.civil_end_time", s, e),
                _range(f"{prefix}.interval.end_time", us, ue),
            ]


def filter_candidates(dt: DataType, window: CivilWindow) -> list[str]:
    """All filters worth trying for ``dt``: own kind first, snake_case then camelCase prefix,
    then other kinds (in case the registry's kind guess is wrong). De-duplicated, ordered."""
    kinds = [dt.kind] + [k for k in (Kind.INTERVAL, Kind.SAMPLE, Kind.DAILY) if k != dt.kind]
    out: list[str] = []
    for kind in kinds:
        for prefix in dict.fromkeys((dt.snake, dt.camel)):
            for f in filter_for(kind, prefix, window):
                if f not in out:
                    out.append(f)
    return out
