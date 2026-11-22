"""`pulse probe`: discover which data types this account actually has, and record fixtures."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pulse.client import HealthApiError, HealthClient, InvalidArgument
from pulse.datatypes import CivilWindow, DataType, filter_candidates, page_size_for
from pulse.fileio import ensure_private_dir, write_private_json
from pulse.scrub import Scrubber

log = logging.getLogger(__name__)

JSON = dict[str, Any]
_EXTRA_FRACTION = re.compile(r"(\.\d{6})\d+")
_SKIP_VALUE_KEYS = {"interval", "sampleTime", "date", "metadata", "stages", "outOfBedSegments"}


class Status(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    ERROR = "error"


@dataclass
class Coverage:
    data_type: str
    status: Status
    points: int = 0
    first: datetime | date | None = None
    last: datetime | date | None = None
    samples: list[str] = field(default_factory=list)
    filter_used: str | None = None
    truncated: bool = False
    error: str | None = None


# ---- pure helpers (unit tested) ---------------------------------------------------------


def _parse_ts(value: str) -> datetime:
    """RFC 3339 with up to nanosecond precision; Python keeps microseconds."""
    return datetime.fromisoformat(_EXTRA_FRACTION.sub(r"\1", value.replace("Z", "+00:00")))


def _civil_date(d: JSON) -> date:
    return date(int(d["year"]), int(d["month"]), int(d["day"]))


def point_value(point: JSON, dt: DataType) -> JSON | None:
    v = point.get(dt.value_field)
    if isinstance(v, dict):
        return v
    # Fallback: first dict-valued key that isn't metadata about the point.
    for k, val in point.items():
        if k not in {"name", "dataPointName", "dataSource"} and isinstance(val, dict):
            return val
    return None


def point_time(value: JSON) -> datetime | date | None:
    """Start instant (or civil date for daily types) of a data point value."""
    if isinstance(value.get("interval"), dict) and "startTime" in value["interval"]:
        return _parse_ts(value["interval"]["startTime"])
    if isinstance(value.get("sampleTime"), dict) and "physicalTime" in value["sampleTime"]:
        return _parse_ts(value["sampleTime"]["physicalTime"])
    if isinstance(value.get("date"), dict):
        return _civil_date(value["date"])
    return None


def _flatten(obj: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not prefix and k in _SKIP_VALUE_KEYS:
                continue
            yield from _flatten(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(obj, list):
        yield (f"{prefix}[]", f"{len(obj)} items")
    else:
        yield (prefix, obj)


def describe_value(value: JSON, max_len: int = 60) -> str:
    parts = [f"{k}={v}" for k, v in _flatten(value)]
    if "stages" in value and isinstance(value["stages"], list):
        parts.append(f"stages={len(value['stages'])}")
    text = ", ".join(parts)
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def summarize(dt: DataType, pages: list[JSON], truncated: bool = False) -> Coverage:
    points = [p for page in pages for p in page.get("dataPoints", []) or []]
    if not points:
        return Coverage(dt.name, Status.EMPTY)
    values = [v for v in (point_value(p, dt) for p in points) if v is not None]
    times = [t for t in (point_time(v) for v in values) if t is not None]
    # Mixed date/datetime can't be compared; normalise to dates only if mixed.
    if times and len({type(t) for t in times}) > 1:
        times = [t.date() if isinstance(t, datetime) else t for t in times]
    samples = [describe_value(v) for v in values[:2]]
    return Coverage(
        dt.name,
        Status.OK,
        points=len(points),
        first=min(times) if times else None,
        last=max(times) if times else None,
        samples=samples,
        truncated=truncated,
    )


# ---- I/O --------------------------------------------------------------------------------


@dataclass
class FixtureWriter:
    root: Path
    scrubber: Scrubber

    def __post_init__(self) -> None:
        ensure_private_dir(self.root)
        ensure_private_dir(self.root / "raw")
        ensure_private_dir(self.root / "scrubbed")

    def write(self, name: str, payload: Any) -> None:
        write_private_json(self.root / "raw" / f"{name}.json", payload)
        write_private_json(self.root / "scrubbed" / f"{name}.json", self.scrubber.scrub(payload))


def probe_type(
    client: HealthClient, dt: DataType, window: CivilWindow, max_pages: int
) -> tuple[Coverage, JSON]:
    """Try candidate filters until one is accepted; return coverage and the raw record."""
    last_err: HealthApiError | None = None
    for flt in filter_candidates(dt, window):
        try:
            pages = list(
                client.list_points(
                    dt.name,
                    filter=flt,
                    page_size=page_size_for(dt),
                    max_pages=max_pages,
                    reconcile=dt.uses_reconcile,
                )
            )
        except InvalidArgument as exc:
            last_err = exc
            log.info("filter rejected for %s: %s", dt.name, flt)
            continue
        except HealthApiError as exc:
            cov = Coverage(dt.name, Status.ERROR, error=f"{exc.status} {exc.code}")
            return cov, {
                "filter": flt,
                "error": {"status": exc.status, "code": exc.code, "message": exc.message},
            }
        truncated = bool(pages and pages[-1].get("nextPageToken"))
        cov = summarize(dt, pages, truncated=truncated)
        cov.filter_used = flt
        return cov, {
            "filter": flt,
            "method": "reconcile" if dt.uses_reconcile else "list",
            "pages": pages,
        }
    err = f"{last_err.status} {last_err.code}" if last_err else "no filter accepted"
    return Coverage(dt.name, Status.ERROR, error=err), {
        "error": {"message": last_err.message if last_err else err}
    }


def run_probe(
    client: HealthClient,
    types: list[DataType],
    zone: ZoneInfo,
    days: int,
    max_pages: int,
    writer: FixtureWriter | None,
    on_progress: Any = None,
) -> tuple[JSON, list[Coverage]]:
    window = CivilWindow.last_days(days, zone)
    meta: JSON = {
        "probed_at": datetime.now(UTC).isoformat(),
        "window": [window.start.isoformat(), window.end.isoformat()],
        "tz": str(zone),
    }
    account: JSON = {}
    for key, fn in (
        ("identity", client.get_identity),
        ("profile", client.get_profile),
        ("settings", client.get_settings),
    ):
        try:
            account[key] = fn()
        except HealthApiError as exc:
            account[key] = {"error": f"{exc.status} {exc.code}: {exc.message}"}
        if writer:
            writer.write(key, account[key])
    results: list[Coverage] = []
    for dt in types:
        if on_progress:
            on_progress(dt.name)
        cov, record = probe_type(client, dt, window, max_pages)
        results.append(cov)
        if writer:
            writer.write(f"datapoints__{dt.name}", {**meta, "data_type": dt.name, **record})
    if writer:
        writer.write(
            "coverage",
            {
                **meta,
                "results": [
                    {
                        "data_type": c.data_type,
                        "status": c.status.value,
                        "points": c.points,
                        "first": c.first.isoformat() if c.first else None,
                        "last": c.last.isoformat() if c.last else None,
                        "filter": c.filter_used,
                        "truncated": c.truncated,
                        "error": c.error,
                    }
                    for c in results
                ],
            },
        )
    return account, results
