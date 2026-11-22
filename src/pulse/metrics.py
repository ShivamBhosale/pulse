"""Catalog of daily metrics: drives tiles, /metrics aggregation and 'hide if no data'."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Agg = Literal["sum", "avg", "max"]
Better = Literal["up", "down", "none"]


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str
    agg: Agg  # how days combine into weeks/months
    better: Better  # which direction is "good" for status colouring
    group: str
    decimals: int = 0


_M = Metric
CATALOG: dict[str, Metric] = {
    m.key: m
    for m in (
        _M("steps", "Steps", "steps", "sum", "up", "activity"),
        _M("distance_km", "Distance", "km", "sum", "up", "activity", 2),
        _M("calories_total", "Calories burned", "kcal", "sum", "none", "activity"),
        _M("calories_active", "Active calories", "kcal", "sum", "up", "activity"),
        _M("azm", "Active zone minutes", "min", "sum", "up", "activity"),
        _M("azm_fat_burn", "AZM fat burn", "min", "sum", "up", "activity"),
        _M("azm_cardio", "AZM cardio", "min", "sum", "up", "activity"),
        _M("azm_peak", "AZM peak", "min", "sum", "up", "activity"),
        _M("sedentary_min", "Sedentary time", "min", "avg", "down", "activity"),
        _M("active_min_light", "Light activity", "min", "sum", "up", "activity"),
        _M("active_min_moderate", "Moderate activity", "min", "sum", "up", "activity"),
        _M("active_min_vigorous", "Vigorous activity", "min", "sum", "up", "activity"),
        _M("resting_hr", "Resting heart rate", "bpm", "avg", "down", "heart"),
        _M("hr_avg", "Average heart rate", "bpm", "avg", "none", "heart"),
        _M("hr_min", "Lowest heart rate", "bpm", "avg", "none", "heart"),
        _M("hr_max", "Highest heart rate", "bpm", "avg", "none", "heart"),
        _M("hrv_rmssd", "Heart rate variability", "ms", "avg", "up", "heart", 1),
        _M("hrv_deep_rmssd", "HRV in deep sleep", "ms", "avg", "up", "heart", 1),
        _M("nonrem_hr", "Non-REM heart rate", "bpm", "avg", "down", "heart"),
        _M("spo2_avg", "Blood oxygen (avg)", "%", "avg", "up", "heart", 1),
        _M("spo2_low", "Blood oxygen (low)", "%", "avg", "up", "heart", 1),
        _M("skin_temp_delta", "Skin temperature variation", "°C", "avg", "none", "heart", 2),
        _M("sleep_min", "Time asleep (incl. naps)", "min", "avg", "up", "sleep"),
        _M("sleep_main_min", "Main sleep", "min", "avg", "up", "sleep"),
        _M("sleep_in_bed_min", "Time in bed", "min", "avg", "none", "sleep"),
        _M("sleep_efficiency", "Sleep efficiency", "%", "avg", "up", "sleep", 1),
        _M("sleep_deep_min", "Deep sleep", "min", "avg", "up", "sleep"),
        _M("sleep_light_min", "Light sleep", "min", "avg", "none", "sleep"),
        _M("sleep_rem_min", "REM sleep", "min", "avg", "up", "sleep"),
        _M("sleep_awake_min", "Awake in bed", "min", "avg", "down", "sleep"),
        _M("bedtime_min", "Bedtime", "min", "avg", "none", "sleep"),
        _M("waketime_min", "Wake time", "min", "avg", "none", "sleep"),
        _M("spo2_high", "Blood oxygen (high)", "%", "avg", "up", "heart", 1),
        _M("skin_temp_nightly", "Skin temperature (nightly)", "°C", "avg", "none", "heart", 2),
        _M("skin_temp_baseline", "Skin temperature (baseline)", "°C", "avg", "none", "heart", 2),
        _M("hr_zone_min_light", "Time in light zone", "min", "sum", "none", "heart"),
        _M("hr_zone_min_moderate", "Time in fat-burn zone", "min", "sum", "up", "heart"),
        _M("hr_zone_min_vigorous", "Time in cardio zone", "min", "sum", "up", "heart"),
        _M("hr_zone_min_peak", "Time in peak zone", "min", "sum", "up", "heart"),
        _M("hr_zone_kcal_light", "Calories in light zone", "kcal", "sum", "none", "activity"),
        _M("hr_zone_kcal_moderate", "Calories in fat-burn zone", "kcal", "sum", "none", "activity"),
        _M("hr_zone_kcal_vigorous", "Calories in cardio zone", "kcal", "sum", "none", "activity"),
        _M("hr_zone_kcal_peak", "Calories in peak zone", "kcal", "sum", "none", "activity"),
        # ---- derived (pulse.derive recomputes these after every sync) ----
        _M("readiness", "Readiness", "score", "avg", "up", "derived"),
        _M("strain", "Strain (AZM-weighted)", "min", "sum", "none", "derived"),
        _M("load_ratio", "Load ratio (7d:28d)", "ratio", "avg", "none", "derived", 2),
        _M("sleep_debt_min", "Sleep debt (7 nights)", "min", "avg", "down", "derived"),
        _M("bedtime_sd_min", "Bedtime variability", "min", "avg", "down", "derived"),
        _M("waketime_sd_min", "Wake time variability", "min", "avg", "down", "derived"),
        _M("azm_week", "AZM this week", "min", "max", "up", "derived"),
        _M("calories_bmr", "Resting calories (est.)", "kcal", "sum", "none", "derived"),
        _M("sedentary_longest_min", "Longest sedentary stretch", "min", "avg", "down", "derived"),
    )
}


DERIVED_KEYS: tuple[str, ...] = tuple(k for k, m in CATALOG.items() if m.group == "derived")
