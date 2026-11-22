"""Phase 2 derived metrics: readiness, sleep debt, consistency, load, streaks, records."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from pulse import derived as D

D0 = date(2026, 3, 1)


def series(values: list[float | None], end: date) -> dict[date, float]:
    """values[-1] lands on ``end``; None entries are omitted."""
    n = len(values)
    return {end - timedelta(days=n - 1 - i): v for i, v in enumerate(values) if v is not None}


# ---- robust score / readiness -------------------------------------------------------------


def test_robust_score_midpoint_and_clamps() -> None:
    b = D.Baseline(median=50, q1=45, q3=55, n=28)  # iqr 10 → spread 15
    assert D.robust_score(50, b) == 50
    assert D.robust_score(65, b) == 100
    assert D.robust_score(200, b) == 100
    assert D.robust_score(35, b) == 0
    assert D.robust_score(65, b, invert=True) == 0


def test_robust_score_flat_baseline_has_spread_floor() -> None:
    b = D.Baseline(median=60, q1=60, q3=60, n=28)  # iqr 0 → floor 5% of 60 = 3
    assert D.robust_score(63, b, invert=True) == 0
    assert D.robust_score(61.5, b) == pytest.approx(75)


def _flat(v: float, end: date, days: int = 29) -> dict[date, float]:
    return series([v] * days, end)


def test_readiness_at_baseline_with_full_sleep() -> None:
    d = D0 + timedelta(days=40)
    r = D.readiness(
        d,
        hrv=_flat(40, d),
        rhr=_flat(60, d),
        sleep_main=_flat(480, d),
        strain=_flat(30, d - timedelta(days=1)),
        sleep_goal_min=480,
    )
    by = {c.key: c for c in r.components}
    assert by["hrv"].score == 50 and by["rhr"].score == 50 and by["sleep"].score == 100
    assert by["strain"].score == 50
    # 0.35*50 + 0.25*50 + 0.25*100 + 0.15*50
    assert r.score == pytest.approx(62.5)
    assert sum(c.weight for c in r.components) == pytest.approx(1)


def test_readiness_strain_rest_day_is_capped() -> None:
    d = D0 + timedelta(days=40)
    strain = _flat(30, d - timedelta(days=2))
    strain[d - timedelta(days=1)] = 0  # rest day yesterday
    r = D.readiness(d, hrv={}, rhr={}, sleep_main={d: 480}, strain=strain, sleep_goal_min=480)
    by = {c.key: c for c in r.components}
    assert by["strain"].score == D.STRAIN_REST_CAP


def test_readiness_renormalises_missing_parts() -> None:
    d = D0 + timedelta(days=40)
    r = D.readiness(d, hrv=_flat(40, d), rhr={}, sleep_main={d: 240}, strain={}, sleep_goal_min=480)
    by = {c.key: c for c in r.components}
    assert by["rhr"].weight == 0 and by["strain"].weight == 0
    assert by["hrv"].weight == pytest.approx(35 / 60)
    assert r.score == pytest.approx(50 * 35 / 60 + 50 * 25 / 60)


def test_readiness_needs_two_parts_including_hrv_or_sleep() -> None:
    d = D0 + timedelta(days=40)
    only_sleep = D.readiness(d, hrv={}, rhr={}, sleep_main={d: 480}, strain={}, sleep_goal_min=480)
    assert only_sleep.score is None
    rhr_strain = D.readiness(
        d,
        hrv={},
        rhr=_flat(60, d),
        sleep_main={},
        strain=_flat(30, d - timedelta(days=1)),
        sleep_goal_min=480,
    )
    assert rhr_strain.score is None


def test_readiness_custom_weights() -> None:
    d = D0 + timedelta(days=40)
    r = D.readiness(
        d,
        hrv=_flat(40, d),
        rhr={},
        sleep_main={d: 480},
        strain={},
        sleep_goal_min=480,
        weights={"hrv": 0, "rhr": 0, "sleep": 1, "strain": 0},
    )
    assert r.score == 100


# ---- sleep debt / consistency ----------------------------------------------------------------


def test_sleep_debt_sums_shortfall_and_skips_missing_nights() -> None:
    d = D0 + timedelta(days=10)
    s = series([500, 420, None, 480, 300, 450, 480], d)  # shortfalls: 60, 180, 30
    assert D.sleep_debt(s, d, 480) == 270
    assert D.sleep_debt({}, d, 480) is None


def test_consistency_wraps_around_midnight() -> None:
    d = D0 + timedelta(days=20)
    # 23:30 (-30 as "before wake-day midnight") and 00:30 (+30), plus a same-day 23:30 (1410)
    s = series([-30, 30, 1410, 30, -30, 30], d)
    sd = D.consistency_sd(s, d)
    assert sd == pytest.approx(30)


def test_consistency_needs_five_nights() -> None:
    d = D0 + timedelta(days=20)
    assert D.consistency_sd(series([0, 10, 20, 30], d), d) is None


def test_clock_wrap() -> None:
    assert D.clock_wrap(21 * 60) == -180
    assert D.clock_wrap(1440) == 0
    assert D.clock_wrap(6 * 60) == 360


# ---- load ratio / weekly ---------------------------------------------------------------------


def test_load_ratio_acute_vs_chronic() -> None:
    d = D0 + timedelta(days=40)
    s = series([10.0] * 21 + [40.0] * 7, d)
    chronic = (10 * 21 + 40 * 7) / 28
    assert D.load_ratio(s, d) == pytest.approx(40 / chronic)


def test_load_ratio_needs_history_and_nonzero_chronic() -> None:
    d = D0 + timedelta(days=40)
    assert D.load_ratio(series([10.0] * 20, d), d) is None
    assert D.load_ratio(series([0.0] * 28, d), d) is None


def test_week_to_date_runs_from_monday() -> None:
    monday = date(2026, 11, 16)
    s = {monday - timedelta(days=1): 99.0, monday: 10.0, monday + timedelta(days=2): 5.0}
    assert D.week_to_date(s, monday + timedelta(days=3)) == 15
    assert D.week_to_date(s, monday - timedelta(days=1)) == 99
    assert D.weekly_totals(s) == {monday - timedelta(days=7): 99.0, monday: 15.0}


def test_derive_daily_emits_expected_keys() -> None:
    d = D0 + timedelta(days=40)
    rows = D.derive_daily(
        {
            "azm": series([20.0] * 41, d),
            "calories_total": {d: 2500.0},
            "calories_active": {d: 600.0},
            "sleep_main_min": series([450.0] * 41, d),
            "bedtime_min": series([-30.0] * 41, d),
            "waketime_min": series([420.0] * 41, d),
            "hrv_rmssd": series([40.0] * 41, d),
            "resting_hr": series([60.0] * 41, d),
        },
        sleep_goal_min=480,
        sedentary_longest={d: 95.0},
    )
    last = {k: v for day, k, v in rows if day == d}
    assert set(last) == set(D.DERIVED_UNITS)
    assert last["calories_bmr"] == 1900
    assert last["sleep_debt_min"] == 7 * 30
    assert last["bedtime_sd_min"] == 0
    assert last["load_ratio"] == pytest.approx(1)
    assert last["strain"] == 20
    assert 0 <= last["readiness"] <= 100


# ---- records / streaks -----------------------------------------------------------------------


def test_best_ties_go_to_first_day() -> None:
    s = {D0: 5.0, D0 + timedelta(days=1): 9.0, D0 + timedelta(days=2): 9.0}
    assert D.best(s) == D.Best(9.0, D0 + timedelta(days=1))
    assert D.best(s, lowest=True) == D.Best(5.0, D0)
    assert D.best({}) is None


def test_rolling_mean_requires_min_points() -> None:
    s = series([60, 62, 64, 66, 68], D0 + timedelta(days=4))
    rm = D.rolling_mean(s)
    assert list(rm) == [D0 + timedelta(days=4)]
    assert rm[D0 + timedelta(days=4)] == 64


def _hits(flags: str, end: date, step: int = 1) -> dict[date, bool]:
    """'1' met, '0' not met, '.' missing; last char is ``end``."""
    n = len(flags)
    return {
        end - timedelta(days=step * (n - 1 - i)): f == "1" for i, f in enumerate(flags) if f != "."
    }


def test_streak_current_and_longest() -> None:
    today = D0 + timedelta(days=30)
    st = D.streak(_hits("1111011100", today), today)
    assert (st.current, st.longest) == (0, 4)
    st = D.streak(_hits("1101111", today), today)
    assert (st.current, st.longest, st.current_start) == (4, 4, today - timedelta(days=3))


def test_streak_today_in_progress_does_not_break() -> None:
    today = D0 + timedelta(days=30)
    st = D.streak(_hits("1110", today), today)
    assert st.current == 3
    st = D.streak(_hits("111.", today), today)  # no data yet today
    assert st.current == 3


def test_streak_missing_day_breaks() -> None:
    today = D0 + timedelta(days=30)
    st = D.streak(_hits("11.11", today), today)
    assert (st.current, st.longest) == (2, 2)


def test_weekly_streak() -> None:
    this_monday = date(2026, 11, 16)
    st = D.streak(_hits("0111", this_monday, step=7), this_monday, step_days=7)
    assert (st.current, st.longest) == (3, 3)


def test_streak_empty() -> None:
    assert D.streak({}, D0) == D.Streak(0, None, 0, None)


# ---- correlation / zones ---------------------------------------------------------------------


def test_pearson_and_strength() -> None:
    assert D.pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1)
    assert D.pearson([1, 2, 3], [5, 5, 5]) is None
    assert D.pearson([1, 2], [1, 2]) is None
    assert D.correlation_strength(-0.62) == "strong negative"
    assert D.correlation_strength(0.2) == "weak positive"
    assert D.correlation_strength(0.05) == "negligible"
    assert D.correlation_strength(None) == "not enough data"


def test_time_in_zones() -> None:
    bounds = {
        "light": (90, 110),
        "moderate": (111, 130),
        "vigorous": (131, 160),
        "peak": (161, 220),
    }
    out = D.time_in_zones([70, 95, 115, 115, 140, 170], bounds)
    assert out == {"light": 1, "moderate": 2, "vigorous": 1, "peak": 1, "below": 1}
