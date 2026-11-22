import json
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pulse.sync import parsers as P

TZ = ZoneInfo("America/Toronto")
AT = datetime(2026, 11, 22, 5, 0, tzinfo=UTC)
API = Path(__file__).parent / "fixtures" / "api"


def load(name: str):
    return json.loads((API / name).read_text())


def daily(batch: P.Batch) -> dict[tuple[date, str], float]:
    return {(r["civil_date"], r["metric"]): r["value"] for r in batch.rows["daily_metrics"]}


# ---- primitives -------------------------------------------------------------------------


def test_parse_ts_nanoseconds_and_offsets():
    assert P.parse_ts("2026-11-21T04:10:00.123456789Z") == datetime(
        2026, 11, 21, 4, 10, 0, 123456, tzinfo=UTC
    )
    assert P.parse_ts("2026-11-21T00:10:00-04:00") == datetime(2026, 11, 21, 4, 10, tzinfo=UTC)


def test_durations_and_numbers():
    assert P.parse_duration_s("42300s") == 42300
    assert P.parse_duration_s("793.173s") == pytest.approx(793.173)
    assert P.parse_duration_s("-18000s") == -18000
    assert P.parse_duration_s(None) == 0
    assert P.num("112") == 112.0 and P.num(None) is None and P.num("") is None
    assert P.inum("41.6") == 42


def test_local_date_uses_api_offset_then_zone_fallback():
    # 03:30Z on the DST fall-back day: EDT (-4h) → still Oct 31 locally.
    ts = datetime(2026, 11, 1, 3, 30, tzinfo=UTC)
    assert P.local_date(ts, "-14400s", TZ) == date(2026, 10, 31)
    assert P.local_date(ts, None, TZ) == date(2026, 10, 31)
    # 05:30Z the same day: EST (-5h) → Nov 1 00:30.
    assert P.local_date(datetime(2026, 11, 1, 5, 30, tzinfo=UTC), "-18000s", TZ) == date(
        2026, 11, 1
    )


def test_point_key_stable_and_source_sensitive():
    v = {"interval": {"startTime": "2026-11-21T14:10:00Z", "endTime": "2026-11-21T14:11:00Z"}}
    band = {"dataSource": {"platform": "FITBIT", "device": {"displayName": "Fitbit Air"}}}
    phone = {"dataSource": {"platform": "HEALTH_CONNECT"}}
    assert P.point_key("steps", band, v) == P.point_key("steps", dict(band), dict(v))
    assert P.point_key("steps", band, v) != P.point_key("steps", phone, v)
    assert P.point_key("sleep", {"dataPointName": "users/x/dataPoints/9"}, v).endswith("/9")


# ---- daily rollups ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data_type", "expected"),
    [
        ("steps", {"steps": 12131}),
        ("distance", {"distance_km": pytest.approx(7.909406)}),
        ("total-calories", {"calories_total": 2264.2}),
        ("active-energy-burned", {"calories_active": 614.0}),
        ("sedentary-period", {"sedentary_min": 705.0}),
        ("heart-rate", {"hr_avg": 78.0, "hr_min": 55, "hr_max": 123}),
        ("active-minutes", {"active_min_light": 222, "active_min_vigorous": 33}),
        ("time-in-heart-rate-zone", {"hr_zone_min_light": 1414.0}),
        ("calories-in-heart-rate-zone", {"hr_zone_kcal_moderate": 215.3}),
    ],
)
def test_daily_rollups(data_type, expected):
    b = P.parse_daily_rollup(data_type, [load("daily_rollups.json")[data_type]])
    got = {m: v for (_, m), v in daily(b).items()}
    assert got == expected
    assert {d for d, _ in daily(b)} == {date(2026, 11, 20)}


def test_empty_rollup_value_is_skipped():
    b = P.parse_daily_rollup("steps", [load("daily_rollups.json")["active-zone-minutes"]])
    assert b.count("daily_metrics") == 0


def test_unknown_rollup_type_raises():
    page = {
        "rollupDataPoints": [
            {
                "civilStartTime": {"date": {"year": 2026, "month": 1, "day": 1}},
                "floors": {"countSum": "3"},
            }
        ]
    }
    with pytest.raises(ValueError):
        P.parse_daily_rollup("floors", [page])


# ---- intraday rollups -------------------------------------------------------------------


def test_hr_rollup_assigns_local_civil_date():
    page = {
        "rollupDataPoints": [
            {
                "startTime": "2026-11-22T04:59:00Z",
                "endTime": "2026-11-22T05:00:00Z",
                "heartRate": {
                    "beatsPerMinuteAvg": 61.5,
                    "beatsPerMinuteMax": 63,
                    "beatsPerMinuteMin": 60,
                },
            },
            {
                "startTime": "2026-11-22T05:00:00Z",
                "endTime": "2026-11-22T05:01:00Z",
                "heartRate": {},
            },
        ]
    }
    rows = P.parse_hr_rollup([page], TZ).rows["intraday_hr"]
    assert len(rows) == 1
    assert rows[0]["civil_date"] == date(2026, 11, 21)  # 23:59 local
    assert (rows[0]["bpm_avg"], rows[0]["bpm_min"], rows[0]["bpm_max"]) == (61.5, 60, 63)


def test_steps_rollup():
    page = {
        "rollupDataPoints": [
            {"startTime": "2026-11-21T14:00:00Z", "steps": {"countSum": "15"}},
            {"startTime": "2026-11-21T14:15:00Z"},
        ]
    }
    rows = P.parse_steps_rollup([page], TZ).rows["intraday_steps"]
    assert [r["steps"] for r in rows] == [15]


# ---- daily lists ------------------------------------------------------------------------


def test_daily_lists():
    pages = load("daily_lists.json")
    b = P.Batch()
    for t, page in pages.items():
        b.extend(P.parse_daily_list(t, [page], TZ, AT))
    d = date(2026, 11, 21)
    got = daily(b)
    assert got[(d, "resting_hr")] == 58
    assert got[(d, "hrv_rmssd")] == 48.5
    assert got[(d, "hrv_deep_rmssd")] == 51.0
    assert got[(d, "nonrem_hr")] == 60
    assert got[(d, "spo2_avg")] == 96.5 and got[(d, "spo2_low")] == 93
    assert got[(d, "skin_temp_delta")] == pytest.approx(0.4)
    zones = {r["zone"]: (r["min_bpm"], r["max_bpm"]) for r in b.rows["hr_zone_bounds"]}
    assert zones == {
        "light": (30, 118),
        "moderate": (119, 143),
        "vigorous": (144, 173),
        "peak": (174, 220),
    }
    assert b.count("raw_points") == 5
    assert all(r["civil_date"] == d for r in b.rows["raw_points"])


# ---- intraday lists ---------------------------------------------------------------------


def test_azm_totals_by_zone_and_zero_fill():
    b = P.parse_azm([load("azm_list.json")], TZ, AT, [date(2026, 11, 20), date(2026, 11, 21)])
    got = daily(b)
    assert got[(date(2026, 11, 21), "azm")] == 3
    assert got[(date(2026, 11, 21), "azm_fat_burn")] == 1
    assert got[(date(2026, 11, 21), "azm_cardio")] == 2
    assert got[(date(2026, 11, 20), "azm")] == 0  # no points, but day was in the window
    assert b.count("raw_points") == 2
    assert len({r["point_key"] for r in b.rows["raw_points"]}) == 2


def test_samples():
    page = {
        "dataPoints": [
            {
                "oxygenSaturation": {
                    "sampleTime": {"physicalTime": "2026-11-21T08:00:00Z", "utcOffset": "-18000s"},
                    "percentage": 95.5,
                }
            }
        ]
    }
    b = P.parse_samples("oxygen-saturation", "spo2", "percentage", [page], TZ, AT)
    (row,) = b.rows["intraday_samples"]
    assert row["metric"] == "spo2" and row["value"] == 95.5
    assert row["civil_date"] == date(2026, 11, 21)


def test_exercise_dedupes_health_connect_duplicate():
    b = P.parse_exercise([load("exercise_list.json")], TZ, AT)
    ex = b.rows["exercises"]
    assert [e["source"] for e in ex] == ["FITBIT/Fitbit Air", "HEALTH_CONNECT"]
    walk = ex[0]
    assert walk["distance_m"] == 2400 and walk["steps"] == 3100 and walk["avg_hr"] == 104
    assert walk["active_s"] == pytest.approx(1790.5)
    assert ex[1]["exercise_type"] == "STRENGTH_TRAINING"
    assert b.count("raw_points") == 3  # raw keeps everything


def test_dedupe_ignores_small_overlap():
    t = lambda h, m: datetime(2026, 1, 1, h, m, tzinfo=UTC)  # noqa: E731
    rows = [
        {"source": "FITBIT", "start_utc": t(10, 0), "end_utc": t(11, 0)},
        {"source": "HEALTH_CONNECT", "start_utc": t(10, 50), "end_utc": t(11, 50)},
    ]
    assert len(P.dedupe_exercises(rows)) == 2


# ---- sleep ------------------------------------------------------------------------------


def test_sleep_sessions_stages_and_daily_metrics():
    b = P.parse_sleep([load("sleep_reconcile.json")], TZ, AT)
    sessions = {s["id"].split("/")[-1]: s for s in b.rows["sleep_sessions"]}
    night = sessions["night-1"]
    assert night["civil_date"] == date(2026, 11, 21)
    assert night["is_main"] and night["minutes_asleep"] == 420
    assert (night["deep_min"], night["light_min"], night["rem_min"], night["awake_min"]) == (
        90,
        240,
        90,
        10,
    )
    assert night["efficiency"] == pytest.approx(97.7)  # 420 / 430
    assert b.count("sleep_stages") == 5
    d = daily(b)
    day = date(2026, 11, 21)
    assert d[(day, "sleep_min")] == 455  # main 420 + nap 35
    assert d[(day, "sleep_in_bed_min")] == 430
    assert d[(day, "bedtime_min")] == -70  # 22:50 the evening before
    assert d[(day, "waketime_min")] == 360  # 06:00
    assert d[(day, "sleep_deep_min")] == 90
    assert sessions["nap-1"]["deep_min"] is None and not sessions["nap-1"]["is_main"]


def test_nan_values_are_treated_as_missing():
    assert P.num("NaN") is None and P.num(float("inf")) is None
    page = {"dataPoints": [{"dailySleepTemperatureDerivations": {
        "date": {"year": 2026, "month": 5, "day": 27},
        "nightlyTemperatureCelsius": 33.6, "baselineTemperatureCelsius": "NaN"}}]}
    b = P.parse_daily_list("daily-sleep-temperature-derivations", [page], TZ, AT)
    assert {m for (_, m) in daily(b)} == {"skin_temp_nightly"}  # no baseline, no delta
    b2 = P.Batch()
    b2.daily(date(2026, 1, 1), "x", float("nan"), "u")
    assert b2.count("daily_metrics") == 0
