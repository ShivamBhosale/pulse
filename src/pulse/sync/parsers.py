"""Pure functions: Google Health API JSON → table rows.

Numbers arrive as JSON strings for int64 fields ("count": "112"), so everything goes through
``num``. Civil dates come from the API's own civil fields or the UTC offset it reports; the
configured zone is only a fallback (rollups don't carry offsets).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

JSON = dict[str, Any]

_EXTRA_FRACTION = re.compile(r"(\.\d{6})\d+")


# ---- primitives ----------------------------------------------------------------------


def parse_ts(value: str) -> datetime:
    """RFC 3339 (up to nanoseconds) → aware UTC datetime."""
    dt = datetime.fromisoformat(_EXTRA_FRACTION.sub(r"\1", value.replace("Z", "+00:00")))
    return dt.astimezone(UTC)


def parse_duration_s(value: str | None) -> float:
    """Protobuf duration "42300s" / "793.173s" / "-18000s" → seconds."""
    if not value:
        return 0.0
    return float(value.rstrip("s"))


def num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def inum(value: Any) -> int | None:
    v = num(value)
    return None if v is None else round(v)


def civil_date_obj(d: JSON) -> date:
    return date(int(d["year"]), int(d["month"]), int(d["day"]))


def local_date(ts: datetime, offset: str | None, zone: ZoneInfo) -> date:
    """Civil date of an instant using the API-reported UTC offset when available."""
    if offset:
        return (ts + timedelta(seconds=parse_duration_s(offset))).date()
    return ts.astimezone(zone).date()


def point_key(data_type: str, point: JSON, value: JSON) -> str:
    """Stable identity for a data point. Uses the API resource name when there is one,
    otherwise a hash of time anchor + source, so re-fetches upsert instead of duplicating."""
    name = point.get("name") or point.get("dataPointName")
    if name:
        return str(name)[-128:]
    anchor: Any = (
        value.get("interval", {}).get("startTime")
        or value.get("sampleTime", {}).get("physicalTime")
        or value.get("date")
    )
    if isinstance(value.get("interval"), dict):
        anchor = f"{anchor}/{value['interval'].get('endTime')}"
    src = point.get("dataSource", {})
    ident = json.dumps(
        [
            data_type,
            anchor,
            src.get("platform"),
            src.get("recordingMethod"),
            (src.get("device") or {}).get("displayName"),
            (src.get("application") or {}).get("packageName"),
            value.get("heartRateZone"),  # AZM has one point per zone per minute
        ],
        sort_keys=True,
        default=str,
    )
    return "h:" + hashlib.sha256(ident.encode()).hexdigest()[:40]


def source_label(point: JSON) -> str:
    src = point.get("dataSource", {}) or {}
    device = (src.get("device") or {}).get("displayName")
    return "/".join(x for x in (src.get("platform"), device) if x) or "unknown"


# ---- batch container -------------------------------------------------------------------


@dataclass
class Batch:
    """Rows per table produced from one fetch."""

    rows: dict[str, list[JSON]] = field(default_factory=lambda: defaultdict(list))

    def add(self, table: str, row: JSON) -> None:
        self.rows[table].append(row)

    def extend(self, other: Batch) -> None:
        for table, rows in other.rows.items():
            self.rows[table].extend(rows)

    def daily(self, d: date, metric: str, value: float | None, unit: str) -> None:
        if value is not None:
            self.add(
                "daily_metrics", {"civil_date": d, "metric": metric, "value": value, "unit": unit}
            )

    def count(self, table: str) -> int:
        return len(self.rows.get(table, []))


def raw_row(data_type: str, point: JSON, value: JSON, civil: date, fetched_at: datetime) -> JSON:
    start = end = None
    if isinstance(value.get("interval"), dict):
        start = parse_ts(value["interval"]["startTime"])
        end = parse_ts(value["interval"]["endTime"])
    elif isinstance(value.get("sampleTime"), dict):
        start = end = parse_ts(value["sampleTime"]["physicalTime"])
    return {
        "data_type": data_type,
        "point_key": point_key(data_type, point, value),
        "civil_date": civil,
        "start_utc": start,
        "end_utc": end,
        "source": source_label(point)[:128],
        "payload_json": json.dumps(point, separators=(",", ":")),
        "fetched_at": fetched_at,
    }


def _value_field(data_type: str) -> str:
    head, *rest = data_type.split("-")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)


def _points(pages: Iterable[JSON]) -> Iterable[JSON]:
    for page in pages:
        yield from page.get("dataPoints", []) or []


def _interval_civil_date(value: JSON, zone: ZoneInfo) -> date:
    iv = value["interval"]
    civil = iv.get("civilStartTime")
    if civil and "date" in civil:
        return civil_date_obj(civil["date"])
    return local_date(parse_ts(iv["startTime"]), iv.get("startUtcOffset"), zone)


def _sample_civil_date(value: JSON, zone: ZoneInfo) -> date:
    st = value["sampleTime"]
    civil = st.get("civilTime")
    if civil and "date" in civil:
        return civil_date_obj(civil["date"])
    return local_date(parse_ts(st["physicalTime"]), st.get("utcOffset"), zone)


# ---- daily rollups (dailyRollUp) ---------------------------------------------------------

_ZONE_KEY = {
    "LIGHT": "light",
    "MODERATE": "moderate",
    "VIGOROUS": "vigorous",
    "PEAK": "peak",
    "FAT_BURN": "fat_burn",
    "CARDIO": "cardio",
}


def _zone(name: str) -> str:
    return _ZONE_KEY.get(name, name.lower())


def parse_daily_rollup(data_type: str, pages: Iterable[JSON]) -> Batch:
    b = Batch()
    for page in pages:
        for p in page.get("rollupDataPoints", []) or []:
            d = civil_date_obj(p["civilStartTime"]["date"])
            v = p.get(_value_field(data_type)) or {}
            if not v:
                continue
            match data_type:
                case "steps":
                    b.daily(d, "steps", num(v.get("countSum")), "count")
                case "distance":
                    mm = num(v.get("millimetersSum"))
                    b.daily(d, "distance_km", None if mm is None else mm / 1e6, "km")
                case "total-calories":
                    b.daily(d, "calories_total", num(v.get("kcalSum")), "kcal")
                case "active-energy-burned":
                    b.daily(d, "calories_active", num(v.get("kcalSum")), "kcal")
                case "sedentary-period":
                    b.daily(d, "sedentary_min", parse_duration_s(v.get("durationSum")) / 60, "min")
                case "heart-rate":
                    b.daily(d, "hr_avg", num(v.get("beatsPerMinuteAvg")), "bpm")
                    b.daily(d, "hr_min", num(v.get("beatsPerMinuteMin")), "bpm")
                    b.daily(d, "hr_max", num(v.get("beatsPerMinuteMax")), "bpm")
                case "active-minutes":
                    for lvl in v.get("activeMinutesRollupByActivityLevel", []):
                        key = f"active_min_{_zone(lvl['activityLevel'])}"
                        b.daily(d, key, num(lvl.get("activeMinutesSum")), "min")
                case "time-in-heart-rate-zone":
                    for z in v.get("timeInHeartRateZones", []):
                        key = f"hr_zone_min_{_zone(z['heartRateZone'])}"
                        b.daily(d, key, parse_duration_s(z.get("duration")) / 60, "min")
                case "calories-in-heart-rate-zone":
                    for z in v.get("caloriesInHeartRateZones", []):
                        key = f"hr_zone_kcal_{_zone(z['heartRateZone'])}"
                        b.daily(d, key, num(z.get("kcal")), "kcal")
                case _:
                    raise ValueError(f"no daily rollup parser for {data_type}")
    return b


# ---- intraday rollups (rollUp) -----------------------------------------------------------


def parse_hr_rollup(pages: Iterable[JSON], zone: ZoneInfo) -> Batch:
    b = Batch()
    for page in pages:
        for p in page.get("rollupDataPoints", []) or []:
            hr = p.get("heartRate")
            if not hr or hr.get("beatsPerMinuteAvg") is None:
                continue
            ts = parse_ts(p["startTime"])
            b.add(
                "intraday_hr",
                {
                    "ts_utc": ts,
                    "civil_date": ts.astimezone(zone).date(),
                    "bpm_avg": float(hr["beatsPerMinuteAvg"]),
                    "bpm_min": inum(hr.get("beatsPerMinuteMin")) or 0,
                    "bpm_max": inum(hr.get("beatsPerMinuteMax")) or 0,
                },
            )
    return b


def parse_steps_rollup(pages: Iterable[JSON], zone: ZoneInfo) -> Batch:
    b = Batch()
    for page in pages:
        for p in page.get("rollupDataPoints", []) or []:
            count = inum((p.get("steps") or {}).get("countSum"))
            if count is None:
                continue
            ts = parse_ts(p["startTime"])
            b.add(
                "intraday_steps",
                {"ts_utc": ts, "civil_date": ts.astimezone(zone).date(), "steps": count},
            )
    return b


# ---- daily list types ------------------------------------------------------------------


def parse_daily_list(
    data_type: str, pages: Iterable[JSON], zone: ZoneInfo, fetched_at: datetime
) -> Batch:
    b = Batch()
    vf = _value_field(data_type)
    for p in _points(pages):
        v = p.get(vf)
        if not isinstance(v, dict) or "date" not in v:
            continue
        d = civil_date_obj(v["date"])
        b.add("raw_points", raw_row(data_type, p, v, d, fetched_at))
        match data_type:
            case "daily-resting-heart-rate":
                b.daily(d, "resting_hr", num(v.get("beatsPerMinute")), "bpm")
            case "daily-heart-rate-variability":
                b.daily(d, "hrv_rmssd", num(v.get("averageHeartRateVariabilityMilliseconds")), "ms")
                b.daily(
                    d,
                    "hrv_deep_rmssd",
                    num(v.get("deepSleepRootMeanSquareOfSuccessiveDifferencesMilliseconds")),
                    "ms",
                )
                b.daily(d, "nonrem_hr", num(v.get("nonRemHeartRateBeatsPerMinute")), "bpm")
            case "daily-oxygen-saturation":
                b.daily(d, "spo2_avg", num(v.get("averagePercentage")), "%")
                b.daily(d, "spo2_low", num(v.get("lowerBoundPercentage")), "%")
                b.daily(d, "spo2_high", num(v.get("upperBoundPercentage")), "%")
            case "daily-sleep-temperature-derivations":
                nightly = num(v.get("nightlyTemperatureCelsius"))
                base = num(v.get("baselineTemperatureCelsius"))
                b.daily(d, "skin_temp_nightly", nightly, "°C")
                b.daily(d, "skin_temp_baseline", base, "°C")
                if nightly is not None and base is not None:
                    b.daily(d, "skin_temp_delta", nightly - base, "°C")
            case "daily-heart-rate-zones":
                for z in v.get("heartRateZones", []):
                    lo, hi = inum(z.get("minBeatsPerMinute")), inum(z.get("maxBeatsPerMinute"))
                    if lo is None or hi is None:
                        continue
                    b.add(
                        "hr_zone_bounds",
                        {
                            "civil_date": d,
                            "zone": _zone(z["heartRateZoneType"]),
                            "min_bpm": lo,
                            "max_bpm": hi,
                        },
                    )
            case _:
                raise ValueError(f"no daily list parser for {data_type}")
    return b


# ---- intraday list types ---------------------------------------------------------------


def parse_azm(
    pages: Iterable[JSON],
    zone: ZoneInfo,
    fetched_at: datetime,
    window_dates: Iterable[date] = (),
) -> Batch:
    """Active zone minutes: raw points + per-day totals (the dailyRollUp is empty for AZM).
    Days in ``window_dates`` without any points get an explicit 0, so "no AZM" isn't "no data"."""
    b = Batch()
    totals: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for d in window_dates:
        totals[d]["total"] += 0.0
    for p in _points(pages):
        v = p.get("activeZoneMinutes")
        if not isinstance(v, dict) or "interval" not in v:
            continue
        d = _interval_civil_date(v, zone)
        b.add("raw_points", raw_row("active-zone-minutes", p, v, d, fetched_at))
        minutes = num(v.get("activeZoneMinutes")) or 0.0
        totals[d]["total"] += minutes
        totals[d][_zone(v.get("heartRateZone", "unknown"))] += minutes
    for d, by_zone in totals.items():
        for key, value in by_zone.items():
            b.daily(d, "azm" if key == "total" else f"azm_{key}", value, "min")
    return b


def parse_samples(
    data_type: str,
    metric: str,
    field_name: str,
    pages: Iterable[JSON],
    zone: ZoneInfo,
    fetched_at: datetime,
) -> Batch:
    b = Batch()
    vf = _value_field(data_type)
    for p in _points(pages):
        v = p.get(vf)
        if not isinstance(v, dict) or "sampleTime" not in v:
            continue
        value = num(v.get(field_name))
        if value is None:
            continue
        d = _sample_civil_date(v, zone)
        b.add("raw_points", raw_row(data_type, p, v, d, fetched_at))
        b.add(
            "intraday_samples",
            {
                "metric": metric,
                "ts_utc": parse_ts(v["sampleTime"]["physicalTime"]),
                "civil_date": d,
                "value": value,
            },
        )
    return b


def parse_sedentary(pages: Iterable[JSON], zone: ZoneInfo, fetched_at: datetime) -> Batch:
    b = Batch()
    for p in _points(pages):
        v = p.get("sedentaryPeriod")
        if isinstance(v, dict) and "interval" in v:
            d = _interval_civil_date(v, zone)
            b.add("raw_points", raw_row("sedentary-period", p, v, d, fetched_at))
    return b


def _overlap_ratio(a: JSON, b: JSON) -> float:
    lo = max(a["start_utc"], b["start_utc"])
    hi = min(a["end_utc"], b["end_utc"])
    shorter = min(a["end_utc"] - a["start_utc"], b["end_utc"] - b["start_utc"])
    if hi <= lo or shorter.total_seconds() <= 0:
        return 0.0
    return float((hi - lo) / shorter)


def dedupe_exercises(rows: list[JSON]) -> list[JSON]:
    """Same workout recorded by the band and by Health Connect: keep the Fitbit one."""
    preferred = sorted(rows, key=lambda r: 0 if r["source"].startswith("FITBIT") else 1)
    kept: list[JSON] = []
    for r in preferred:
        if not any(_overlap_ratio(r, k) > 0.5 for k in kept):
            kept.append(r)
    return sorted(kept, key=lambda r: r["start_utc"])


def parse_exercise(pages: Iterable[JSON], zone: ZoneInfo, fetched_at: datetime) -> Batch:
    b = Batch()
    rows: list[JSON] = []
    for p in _points(pages):
        v = p.get("exercise")
        if not isinstance(v, dict) or "interval" not in v:
            continue
        iv = v["interval"]
        start, end = parse_ts(iv["startTime"]), parse_ts(iv["endTime"])
        d = local_date(start, iv.get("startUtcOffset"), zone)
        b.add("raw_points", raw_row("exercise", p, v, d, fetched_at))
        m = v.get("metricsSummary") or {}
        dist_mm = num(m.get("distanceMillimeters"))
        rows.append(
            {
                "id": point_key("exercise", p, v),
                "civil_date": d,
                "start_utc": start,
                "end_utc": end,
                "exercise_type": v.get("exerciseType", "UNKNOWN"),
                "name": v.get("displayName"),
                "active_s": parse_duration_s(v.get("activeDuration")) or None,
                "distance_m": None if dist_mm is None else dist_mm / 1000,
                "steps": inum(m.get("steps")),
                "kcal": num(m.get("caloriesKcal")),
                "avg_hr": num(m.get("averageHeartRateBeatsPerMinute")),
                "source": source_label(p)[:64],
            }
        )
    for r in dedupe_exercises(rows):
        b.add("exercises", r)
    return b


# ---- sleep (reconcile) -------------------------------------------------------------------

_STAGE_COLS = {"DEEP": "deep_min", "LIGHT": "light_min", "REM": "rem_min", "AWAKE": "awake_min"}


def _local_minutes(ts: datetime, offset_s: float, anchor: date) -> float:
    """Minutes from local midnight of ``anchor`` (negative = evening before)."""
    local = ts + timedelta(seconds=offset_s)
    midnight = datetime(anchor.year, anchor.month, anchor.day, tzinfo=UTC)
    return (local - midnight).total_seconds() / 60


def parse_sleep(pages: Iterable[JSON], zone: ZoneInfo, fetched_at: datetime) -> Batch:
    b = Batch()
    sessions: list[JSON] = []
    for p in _points(pages):
        v = p.get("sleep")
        if not isinstance(v, dict) or "interval" not in v:
            continue
        iv = v["interval"]
        start, end = parse_ts(iv["startTime"]), parse_ts(iv["endTime"])
        start_off = parse_duration_s(iv.get("startUtcOffset"))
        end_off = parse_duration_s(iv.get("endUtcOffset"))
        wake_date = local_date(end, iv.get("endUtcOffset"), zone)
        sid = point_key("sleep", p, v)
        b.add("raw_points", raw_row("sleep", p, v, wake_date, fetched_at))
        s = v.get("summary") or {}
        stage_mins = {
            _STAGE_COLS[x["type"]]: inum(x.get("minutes"))
            for x in s.get("stagesSummary", [])
            if x.get("type") in _STAGE_COLS
        }
        in_bed = (end - start).total_seconds() / 60
        asleep = inum(s.get("minutesAsleep")) or 0
        session = {
            "id": sid,
            "civil_date": wake_date,
            "start_utc": start,
            "end_utc": end,
            "is_main": bool((v.get("metadata") or {}).get("mainSleep", False)),
            "sleep_type": v.get("type", "UNKNOWN"),
            "minutes_in_period": inum(s.get("minutesInSleepPeriod")) or round(in_bed),
            "minutes_asleep": asleep,
            "minutes_awake": inum(s.get("minutesAwake")) or 0,
            "minutes_to_fall_asleep": inum(s.get("minutesToFallAsleep")) or 0,
            "minutes_after_wake": inum(s.get("minutesAfterWakeUp")) or 0,
            "deep_min": stage_mins.get("deep_min"),
            "light_min": stage_mins.get("light_min"),
            "rem_min": stage_mins.get("rem_min"),
            "awake_min": stage_mins.get("awake_min"),
            "efficiency": round(100 * asleep / in_bed, 1) if in_bed > 0 else None,
            "start_offset_s": round(start_off),
            "end_offset_s": round(end_off),
        }
        sessions.append(session)
        b.add("sleep_sessions", session)
        for st in v.get("stages", []) or []:
            b.add(
                "sleep_stages",
                {
                    "session_id": sid,
                    "stage": st.get("type", "UNKNOWN"),
                    "start_utc": parse_ts(st["startTime"]),
                    "end_utc": parse_ts(st["endTime"]),
                },
            )
    # Daily sleep metrics: totals across all sessions; timing/stages from the main sleep.
    by_date: dict[date, list[JSON]] = defaultdict(list)
    for s in sessions:
        by_date[s["civil_date"]].append(s)
    for d, ss in by_date.items():
        main = next((s for s in ss if s["is_main"]), max(ss, key=lambda s: s["minutes_asleep"]))
        b.daily(d, "sleep_min", float(sum(s["minutes_asleep"] for s in ss)), "min")
        b.daily(
            d, "sleep_in_bed_min", (main["end_utc"] - main["start_utc"]).total_seconds() / 60, "min"
        )
        b.daily(d, "sleep_efficiency", main["efficiency"], "%")
        for col in ("deep_min", "light_min", "rem_min", "awake_min"):
            val = main[col]
            b.daily(d, f"sleep_{col}", None if val is None else float(val), "min")
        b.daily(
            d, "bedtime_min", _local_minutes(main["start_utc"], main["start_offset_s"], d), "min"
        )
        b.daily(d, "waketime_min", _local_minutes(main["end_utc"], main["end_offset_s"], d), "min")
    return b
