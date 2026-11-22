from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from pulse.datatypes import (
    REGISTRY,
    CivilWindow,
    Kind,
    filter_candidates,
    filter_for,
    page_size_for,
)

TZ = ZoneInfo("America/Toronto")

REQUESTED = [
    "steps",
    "heart-rate",
    "daily-resting-heart-rate",
    "sleep",
    "daily-heart-rate-variability",
    "heart-rate-variability",
    "active-zone-minutes",
    "total-calories",
    "active-energy-burned",
    "basal-energy-burned",
    "calories-in-heart-rate-zone",
    "daily-oxygen-saturation",
    "oxygen-saturation",
    "daily-sleep-temperature-derivations",
    "distance",
    "floors",
    "altitude",
    "exercise",
    "sedentary-period",
    "activity-level",
    "vo2-max",
    "run-vo2-max",
    "weight",
    "body-fat",
]


def test_registry_covers_requested_types_in_order():
    assert list(REGISTRY) == REQUESTED


def test_name_casing():
    dt = REGISTRY["daily-sleep-temperature-derivations"]
    assert dt.snake == "daily_sleep_temperature_derivations"
    assert dt.camel == "dailySleepTemperatureDerivations"
    assert REGISTRY["run-vo2-max"].value_field == "runVo2Max"
    assert REGISTRY["steps"].camel == "steps"


def test_page_sizes_and_reconcile():
    assert page_size_for(REGISTRY["sleep"]) == 25
    assert page_size_for(REGISTRY["exercise"]) == 25
    assert page_size_for(REGISTRY["heart-rate"]) == 10_000
    assert REGISTRY["sleep"].uses_reconcile
    assert not REGISTRY["steps"].uses_reconcile


def test_last_days_window_is_half_open():
    w = CivilWindow.last_days(7, TZ, today=date(2026, 11, 21))
    assert (w.start, w.end) == (date(2026, 11, 15), date(2026, 11, 22))


def test_utc_bounds_across_dst_fall_back():
    # 2026-11-01 is the fall-back day in Toronto: a 25-hour civil day.
    w = CivilWindow(date(2026, 11, 1), date(2026, 11, 2), TZ)
    s, e = w.utc_bounds()
    assert s == datetime(2026, 11, 1, 4, 0, tzinfo=UTC)  # EDT midnight
    assert e == datetime(2026, 11, 2, 5, 0, tzinfo=UTC)  # EST midnight
    assert (e - s).total_seconds() == 25 * 3600


def test_utc_bounds_across_dst_spring_forward():
    w = CivilWindow(date(2026, 3, 8), date(2026, 3, 9), TZ)
    s, e = w.utc_bounds()
    assert (e - s).total_seconds() == 23 * 3600


def test_filter_shapes_per_kind():
    w = CivilWindow(date(2026, 11, 15), date(2026, 11, 22), TZ)
    assert filter_for(Kind.INTERVAL, "steps", w)[0] == (
        'steps.interval.civil_start_time >= "2026-11-15" AND '
        'steps.interval.civil_start_time < "2026-11-22"'
    )
    assert filter_for(Kind.SAMPLE, "heart_rate", w)[0] == (
        'heart_rate.sample_time.physical_time >= "2026-11-15T05:00:00Z" AND '
        'heart_rate.sample_time.physical_time < "2026-11-22T05:00:00Z"'
    )
    assert filter_for(Kind.DAILY, "daily_resting_heart_rate", w) == [
        'daily_resting_heart_rate.date >= "2026-11-15" AND '
        'daily_resting_heart_rate.date < "2026-11-22"'
    ]
    assert filter_for(Kind.SLEEP, "sleep", w)[0].startswith("sleep.interval.civil_end_time >= ")


def test_candidates_prefer_own_kind_snake_case_and_dedupe():
    w = CivilWindow(date(2026, 11, 15), date(2026, 11, 22), TZ)
    c = filter_candidates(REGISTRY["daily-heart-rate-variability"], w)
    assert c[0].startswith("daily_heart_rate_variability.date")
    assert c[1].startswith("dailyHeartRateVariability.date")
    assert len(c) == len(set(c))
    # steps has identical snake/camel names, so no duplicates
    s = filter_candidates(REGISTRY["steps"], w)
    assert len(s) == len(set(s))
