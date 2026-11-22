"""Pure derived-metric maths: baselines, status, medians. No I/O."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

Status = Literal["in_range", "mild", "notable", "none"]
BASELINE_DAYS = 28
MIN_BASELINE_POINTS = 7


@dataclass(frozen=True)
class Baseline:
    median: float
    q1: float
    q3: float
    n: int

    @property
    def iqr(self) -> float:
        return self.q3 - self.q1


def baseline(
    values: Sequence[float | None], min_points: int = MIN_BASELINE_POINTS
) -> Baseline | None:
    """Median and quartiles of the window (caller excludes the current day)."""
    vals = sorted(v for v in values if v is not None)
    if len(vals) < min_points:
        return None
    q1, med, q3 = statistics.quantiles(vals, n=4, method="inclusive")
    return Baseline(median=med, q1=q1, q3=q3, n=len(vals))


def status(value: float | None, b: Baseline | None) -> Status:
    """in_range inside the IQR; notable beyond 1.5 x IQR from the median; mild otherwise."""
    if value is None or b is None:
        return "none"
    if b.q1 <= value <= b.q3:
        return "in_range"
    if abs(value - b.median) > 1.5 * b.iqr:
        return "notable"
    return "mild"


def delta(value: float | None, b: Baseline | None) -> float | None:
    if value is None or b is None:
        return None
    return value - b.median


def cumulative(slots: Sequence[float]) -> list[float]:
    out: list[float] = []
    total = 0.0
    for v in slots:
        total += v
        out.append(total)
    return out


def median_curve(curves: Sequence[Sequence[float]]) -> list[float]:
    """Point-wise median of equal-length curves (e.g. cumulative steps per 15-min slot)."""
    if not curves:
        return []
    width = len(curves[0])
    return [statistics.median(c[i] for c in curves) for i in range(width)]


def stdev(values: Sequence[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.pstdev(vals) if len(vals) >= 2 else None


# ==== Phase 2: derived daily series, readiness, records ======================================
#
# Everything below is pure: inputs are {date: value} series, outputs are plain values. The
# I/O wrapper (pulse.derive) loads series from daily_metrics and writes the results back.

Series = Mapping[date, float]

READINESS_DEFAULT_WEIGHTS: dict[str, float] = {"hrv": 35, "rhr": 25, "sleep": 25, "strain": 15}
STRAIN_REST_CAP = 70.0  # under-load can't push the strain component above this
CONSISTENCY_DAYS = 14
CONSISTENCY_MIN_NIGHTS = 5
DEBT_NIGHTS = 7
ACUTE_DAYS, CHRONIC_DAYS, CHRONIC_MIN_POINTS = 7, 28, 21


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def trailing(values: Series, d: date, days: int, *, include_day: bool) -> list[float | None]:
    """Values for the ``days`` days ending at d (inclusive) or the day before (exclusive)."""
    first = 0 if include_day else 1
    return [values.get(d - timedelta(days=i)) for i in range(first, first + days)]


def baseline_at(values: Series, d: date, days: int = BASELINE_DAYS) -> Baseline | None:
    """28-day median/IQR excluding d itself."""
    return baseline(trailing(values, d, days, include_day=False))


def robust_score(value: float, b: Baseline, *, invert: bool = False) -> float:
    """0-100 score: 50 at the median, 0/100 at 1.5 x IQR either side (clamped).
    The spread has a floor (5% of the median, at least 1) so a flat baseline can't explode."""
    spread = max(1.5 * b.iqr, 0.05 * abs(b.median), 1.0)
    z = _clamp((value - b.median) / spread, -1.0, 1.0)
    return 50.0 + 50.0 * (-z if invert else z)


@dataclass(frozen=True)
class Component:
    key: str  # hrv | rhr | sleep | strain
    score: float | None
    weight: float  # effective (renormalised) weight, 0 when the component is missing
    value: float | None
    reference: float | None  # baseline median or goal the value was compared with


@dataclass(frozen=True)
class Readiness:
    score: float | None
    components: tuple[Component, ...]


READINESS_FORMULA = (
    "Personal heuristic, not a medical measure. Weighted mean of four 0-100 parts: "
    "HRV vs your 28-day median (higher is better), resting HR vs your 28-day median "
    "(lower is better), last night's main sleep vs your goal (capped at 100), and yesterday's "
    "strain vs your 28-day median (lower scores higher, capped at 70). HRV and resting HR "
    "score 50 at your median and reach 0 or 100 at 1.5 x IQR away. Missing parts are left "
    "out and the remaining weights rescaled; at least two parts, including HRV or sleep, "
    "are needed."
)


def readiness(
    d: date,
    *,
    hrv: Series,
    rhr: Series,
    sleep_main: Series,
    strain: Series,
    sleep_goal_min: float,
    weights: Mapping[str, float] = READINESS_DEFAULT_WEIGHTS,
) -> Readiness:
    """Readiness for civil day d (HRV, RHR and sleep of the night ending on d; strain of d-1)."""
    parts: dict[str, tuple[float | None, float | None, float | None]] = {}

    def vs_baseline(key: str, series: Series, day: date, invert: bool) -> None:
        v, b = series.get(day), baseline_at(series, day)
        score = robust_score(v, b, invert=invert) if v is not None and b is not None else None
        parts[key] = (score, v, b.median if b else None)

    vs_baseline("hrv", hrv, d, invert=False)
    vs_baseline("rhr", rhr, d, invert=True)
    s = sleep_main.get(d)
    parts["sleep"] = (
        min(100.0, s / sleep_goal_min * 100.0) if s is not None and sleep_goal_min > 0 else None,
        s,
        sleep_goal_min,
    )
    vs_baseline("strain", strain, d - timedelta(days=1), invert=True)
    strain_score = parts["strain"][0]
    if strain_score is not None:
        parts["strain"] = (min(STRAIN_REST_CAP, strain_score), *parts["strain"][1:])

    present = {k for k, (score, _, _) in parts.items() if score is not None}
    total_w = sum(max(0.0, weights.get(k, 0.0)) for k in present)
    enough = len(present) >= 2 and bool(present & {"hrv", "sleep"}) and total_w > 0
    comps = tuple(
        Component(
            key=k,
            score=None if sc is None else round(sc, 1),
            weight=(max(0.0, weights.get(k, 0.0)) / total_w) if enough and k in present else 0.0,
            value=v,
            reference=ref,
        )
        for k, (sc, v, ref) in parts.items()
    )
    if not enough:
        return Readiness(None, comps)
    score = sum(c.score * c.weight for c in comps if c.score is not None)
    return Readiness(round(score, 1), comps)


def sleep_debt(sleep_main: Series, d: date, goal_min: float) -> float | None:
    """Sum of max(0, goal - actual) over the 7 nights ending on d. Missing nights are skipped."""
    nights = [v for v in trailing(sleep_main, d, DEBT_NIGHTS, include_day=True) if v is not None]
    return sum(max(0.0, goal_min - v) for v in nights) if nights else None


def consistency_sd(times: Series, d: date) -> float | None:
    """14-day SD of bed/wake times (minutes from local midnight of the wake day, wrapped by
    ``clock_wrap`` so 23:30 and 00:30 are an hour apart, not 23)."""
    vals = [
        clock_wrap(v)
        for v in trailing(times, d, CONSISTENCY_DAYS, include_day=True)
        if v is not None
    ]
    return statistics.pstdev(vals) if len(vals) >= CONSISTENCY_MIN_NIGHTS else None


def clock_wrap(minutes: float) -> float:
    """Map a time of day onto [-6h, 18h) around midnight, so 21:00 is -180 and 24:00 is 0;
    keeps late-evening and after-midnight times on one continuous scale."""
    return ((minutes + 360) % 1440) - 360


def load_ratio(strain: Series, d: date) -> float | None:
    """Acute:chronic load: mean strain of the last 7 days / mean of the last 28 (missing = 0
    only within the covered span; needs 21 days of history)."""
    chronic_vals = trailing(strain, d, CHRONIC_DAYS, include_day=True)
    if sum(v is not None for v in chronic_vals) < CHRONIC_MIN_POINTS:
        return None
    chronic = sum(v or 0.0 for v in chronic_vals) / CHRONIC_DAYS
    acute = sum(v or 0.0 for v in trailing(strain, d, ACUTE_DAYS, include_day=True)) / ACUTE_DAYS
    return acute / chronic if chronic > 0 else None


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_to_date(values: Series, d: date) -> float | None:
    """Running Monday-to-d total (None if no day of the week so far has data)."""
    days = [values.get(week_start(d) + timedelta(days=i)) for i in range(d.weekday() + 1)]
    present = [v for v in days if v is not None]
    return sum(present) if present else None


def weekly_totals(values: Series) -> dict[date, float]:
    out: dict[date, float] = {}
    for d, v in values.items():
        out[week_start(d)] = out.get(week_start(d), 0.0) + v
    return out


DERIVED_UNITS: dict[str, str] = {
    "readiness": "score",
    "strain": "min",
    "load_ratio": "ratio",
    "sleep_debt_min": "min",
    "bedtime_sd_min": "min",
    "waketime_sd_min": "min",
    "azm_week": "min",
    "calories_bmr": "kcal",
    "sedentary_longest_min": "min",
}


def derive_daily(
    series: Mapping[str, Series],
    *,
    sleep_goal_min: float,
    weights: Mapping[str, float] = READINESS_DEFAULT_WEIGHTS,
    sedentary_longest: Series | None = None,
) -> list[tuple[date, str, float]]:
    """All derived (date, metric, value) rows from the synced daily series."""

    def get(key: str) -> Series:
        return series.get(key, {})

    azm, total, active = get("azm"), get("calories_total"), get("calories_active")
    sleep_main, bed, wake = get("sleep_main_min"), get("bedtime_min"), get("waketime_min")
    strain = dict(azm)  # Fitbit AZM already weights cardio/peak minutes x2
    days = sorted({d for s in series.values() for d in s})
    out: list[tuple[date, str, float]] = []

    def put(d: date, key: str, value: float | None) -> None:
        if value is not None and math.isfinite(value):
            out.append((d, key, value))

    for d in days:
        put(d, "strain", strain.get(d))
        put(d, "load_ratio", load_ratio(strain, d))
        put(d, "azm_week", week_to_date(azm, d))
        if d in total and d in active:
            put(d, "calories_bmr", max(0.0, total[d] - active[d]))
        if sleep_main:
            put(d, "sleep_debt_min", sleep_debt(sleep_main, d, sleep_goal_min))
            put(d, "bedtime_sd_min", consistency_sd(bed, d))
            put(d, "waketime_sd_min", consistency_sd(wake, d))
        r = readiness(
            d,
            hrv=get("hrv_rmssd"),
            rhr=get("resting_hr"),
            sleep_main=sleep_main,
            strain=strain,
            sleep_goal_min=sleep_goal_min,
            weights=weights,
        )
        put(d, "readiness", r.score)
    for d, v in (sedentary_longest or {}).items():
        put(d, "sedentary_longest_min", v)
    return out


# ---- records & streaks ---------------------------------------------------------------------


@dataclass(frozen=True)
class Best:
    value: float
    date: date


def best(values: Series, *, lowest: bool = False) -> Best | None:
    """Highest (or lowest) value; ties go to the earliest day, which set the record first."""
    if not values:
        return None
    if lowest:
        d = min(values, key=lambda k: (values[k], k.toordinal()))
    else:
        d = max(values, key=lambda k: (values[k], -k.toordinal()))
    return Best(values[d], d)


def rolling_mean(values: Series, days: int = 7, min_points: int = 5) -> dict[date, float]:
    """Trailing mean per day (only where at least ``min_points`` of the window exist)."""
    out: dict[date, float] = {}
    for d in values:
        window = [v for v in trailing(values, d, days, include_day=True) if v is not None]
        if len(window) >= min_points:
            out[d] = sum(window) / len(window)
    return out


@dataclass(frozen=True)
class Streak:
    current: int
    current_start: date | None
    longest: int
    longest_end: date | None


def streak(hits: Mapping[date, bool], current_period: date, step_days: int = 1) -> Streak:
    """Consecutive periods meeting a goal. ``hits`` maps period keys (days, or Mondays with
    step_days=7) to met/not met; a missing period breaks a streak. The current period is in
    progress: if met it extends the streak, if not it doesn't break it."""
    if not hits:
        return Streak(0, None, 0, None)
    step = timedelta(days=step_days)
    first = min(hits)
    longest, longest_end, run, run_start = 0, None, 0, None
    p = first
    while p < current_period:
        if hits.get(p):
            run_start = p if run == 0 else run_start
            run += 1
            if run > longest:
                longest, longest_end = run, p
        else:
            run, run_start = 0, None
        p += step
    if hits.get(current_period):
        run_start = current_period if run == 0 else run_start
        run += 1
        if run > longest:
            longest, longest_end = run, current_period
    return Streak(run, run_start if run else None, longest, longest_end)


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    try:
        return statistics.correlation(xs, ys)
    except statistics.StatisticsError:  # zero variance
        return None


def correlation_strength(r: float | None) -> str:
    if r is None:
        return "not enough data"
    a = abs(r)
    word = "negligible" if a < 0.1 else "weak" if a < 0.3 else "moderate" if a < 0.5 else "strong"
    if word == "negligible":
        return word
    return f"{word} {'positive' if r > 0 else 'negative'}"


def time_in_zones(bpms: Sequence[float], bounds: Mapping[str, tuple[int, int]]) -> dict[str, int]:
    """Minutes per HR zone for 1-minute average BPMs; below every zone counts as 'below'."""
    out = {z: 0 for z in bounds} | {"below": 0}
    ordered = sorted(bounds.items(), key=lambda kv: kv[1][0], reverse=True)
    for bpm in bpms:
        zone = next((z for z, (lo, _) in ordered if bpm >= lo), "below")
        out[zone] += 1
    return out
