"""Catalog of daily metrics: drives tiles, /metrics aggregation and 'hide if no data'."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Agg = Literal["sum", "avg"]
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
        _M("sleep_min", "Time asleep", "min", "avg", "up", "sleep"),
        _M("sleep_in_bed_min", "Time in bed", "min", "avg", "none", "sleep"),
        _M("sleep_efficiency", "Sleep efficiency", "%", "avg", "up", "sleep", 1),
        _M("sleep_deep_min", "Deep sleep", "min", "avg", "up", "sleep"),
        _M("sleep_light_min", "Light sleep", "min", "avg", "none", "sleep"),
        _M("sleep_rem_min", "REM sleep", "min", "avg", "up", "sleep"),
        _M("sleep_awake_min", "Awake in bed", "min", "avg", "down", "sleep"),
        _M("bedtime_min", "Bedtime", "min", "avg", "none", "sleep"),
        _M("waketime_min", "Wake time", "min", "avg", "none", "sleep"),
    )
}
