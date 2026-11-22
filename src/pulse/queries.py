"""Read-side queries for the API. Aggregation happens in SQL or small server-side loops,
never in the browser."""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from pulse import derived, journal, prefs, summary
from pulse.api import schemas as S
from pulse.datatypes import CivilWindow
from pulse.metrics import CATALOG, Metric
from pulse.models import (
    DailyMetric,
    Exercise,
    HrZoneBound,
    IntradayHR,
    IntradaySteps,
    SleepSession,
    SleepStage,
    SyncState,
    Tag,
)

SLOT_MIN = 15
SLOTS = 24 * 60 // SLOT_MIN
SPARK_DAYS = 14


# ---- basic daily series ------------------------------------------------------------------


def daily_values(session: Session, metric: str, start: date, end: date) -> dict[date, float]:
    """{civil_date: value} for [start, end)."""
    rows = session.execute(
        select(DailyMetric.civil_date, DailyMetric.value).where(
            DailyMetric.metric == metric,
            DailyMetric.civil_date >= start,
            DailyMetric.civil_date < end,
        )
    ).all()
    return {d: v for d, v in rows}


def spark(
    values: dict[date, float], end_inclusive: date, days: int = SPARK_DAYS
) -> list[S.DayValue]:
    return [
        S.DayValue(date=d, value=values.get(d))
        for d in (end_inclusive - timedelta(days=days - 1 - i) for i in range(days))
    ]


def _baseline_out(b: derived.Baseline | None) -> S.BaselineOut | None:
    return None if b is None else S.BaselineOut(median=b.median, q1=b.q1, q3=b.q3, n=b.n)


def daily_tile(
    session: Session,
    metric: str,
    d: date,
    *,
    fallback_days: int = 0,
    note: str | None = None,
    goal: float | None = None,
    label: str | None = None,
) -> S.Tile:
    """Tile for a once-a-day metric. Falls back up to ``fallback_days`` if today isn't in yet."""
    m = CATALOG[metric]
    values = daily_values(
        session, metric, d - timedelta(days=derived.BASELINE_DAYS + 7), d + timedelta(days=1)
    )
    value_date = next(
        (
            d - timedelta(days=i)
            for i in range(fallback_days + 1)
            if d - timedelta(days=i) in values
        ),
        None,
    )
    value = values.get(value_date) if value_date else None
    ref = value_date or d
    window = [values.get(ref - timedelta(days=i)) for i in range(1, derived.BASELINE_DAYS + 1)]
    b = derived.baseline(window)
    if value_date and value_date != d and note is None:
        note = "yesterday" if (d - value_date).days == 1 else f"as of {value_date.isoformat()}"
    return S.Tile(
        key=metric,
        label=label or m.label,
        unit=m.unit,
        value=value,
        value_date=value_date,
        delta=derived.delta(value, b),
        status=derived.status(value, b),
        better=m.better,
        baseline=_baseline_out(b),
        spark=spark(values, d),
        note=note,
        goal=goal,
    )


# ---- "so far today" tiles ----------------------------------------------------------------


def _slot(ts: datetime, zone: ZoneInfo) -> int:
    local = ts.astimezone(zone)
    return (local.hour * 60 + local.minute) // SLOT_MIN


def step_slots(session: Session, start: date, end: date, zone: ZoneInfo) -> dict[date, list[float]]:
    rows = session.execute(
        select(IntradaySteps.civil_date, IntradaySteps.ts_utc, IntradaySteps.steps).where(
            IntradaySteps.civil_date >= start, IntradaySteps.civil_date < end
        )
    ).all()
    out: dict[date, list[float]] = defaultdict(lambda: [0.0] * SLOTS)
    for d, ts, steps in rows:
        out[d][_slot(ts, zone)] += steps
    return dict(out)


def steps_curve(session: Session, d: date, now: datetime, zone: ZoneInfo) -> S.StepsCurve:
    slots = step_slots(
        session, d - timedelta(days=derived.BASELINE_DAYS), d + timedelta(days=1), zone
    )
    history = [derived.cumulative(v) for k, v in slots.items() if k < d]
    today_cum = derived.cumulative(slots.get(d, [0.0] * SLOTS))
    is_today = now.astimezone(zone).date() == d
    cut = _slot(now, zone) if is_today else SLOTS - 1
    return S.StepsCurve(
        today=[v if i <= cut else None for i, v in enumerate(today_cum)],
        median=derived.median_curve(history),
        days_in_median=len(history),
    )


def steps_so_far_tile(
    session: Session, d: date, now: datetime, zone: ZoneInfo, goal: int
) -> S.Tile:
    m = CATALOG["steps"]
    totals = daily_values(session, "steps", d - timedelta(days=SPARK_DAYS), d + timedelta(days=1))
    slots = step_slots(session, d - timedelta(days=derived.BASELINE_DAYS), d, zone)
    cut = _slot(now, zone) if now.astimezone(zone).date() == d else SLOTS - 1
    so_far = [sum(v[: cut + 1]) for v in slots.values()]
    b = derived.baseline(so_far)
    value = totals.get(d)
    return S.Tile(
        key="steps",
        label="Steps so far",
        unit=m.unit,
        value=value,
        value_date=d if value is not None else None,
        delta=derived.delta(value, b),
        status=derived.status(value, b),
        better="up",
        baseline=_baseline_out(b),
        spark=spark(totals, d),
        goal=goal,
        note="vs. your usual by this time",
    )


def azm_so_far_tile(
    session: Session, d: date, now: datetime, zone: ZoneInfo, weekly_goal: int
) -> S.Tile:
    m = CATALOG["azm"]
    totals = daily_values(
        session, "azm", d - timedelta(days=derived.BASELINE_DAYS), d + timedelta(days=1)
    )
    rows = session.execute(
        text(
            "SELECT civil_date, start_utc, "
            "CAST(json_extract(payload_json, '$.activeZoneMinutes.activeZoneMinutes') AS REAL) "
            "FROM raw_points WHERE data_type = 'active-zone-minutes' "
            "AND civil_date >= :lo AND civil_date < :hi"
        ),
        {"lo": (d - timedelta(days=derived.BASELINE_DAYS)).isoformat(), "hi": d.isoformat()},
    ).all()
    cut_minutes = (
        now.astimezone(zone).hour * 60 + now.astimezone(zone).minute
        if now.astimezone(zone).date() == d
        else 24 * 60
    )
    so_far: dict[date, float] = {k: 0.0 for k in totals if k < d}
    for civil, start, minutes in rows:
        civil_d = date.fromisoformat(civil) if isinstance(civil, str) else civil
        ts = datetime.fromisoformat(start).replace(tzinfo=UTC) if isinstance(start, str) else start
        local = ts.astimezone(zone)
        if local.hour * 60 + local.minute < cut_minutes and civil_d in so_far:
            so_far[civil_d] += minutes or 0.0
    b = derived.baseline(list(so_far.values()))
    value = totals.get(d)
    week_start = d - timedelta(days=d.weekday())
    week_total = sum(v for k, v in totals.items() if week_start <= k <= d)
    return S.Tile(
        key="azm",
        label="Active zone minutes",
        unit=m.unit,
        value=value,
        value_date=d if value is not None else None,
        delta=derived.delta(value, b),
        status=derived.status(value, b),
        better="up",
        baseline=_baseline_out(b),
        spark=spark(totals, d),
        goal=weekly_goal,
        note=f"{week_total:.0f} of {weekly_goal} this week",
    )


_COMPONENT_META: dict[str, tuple[str, str]] = {
    "hrv": ("HRV vs baseline", "ms"),
    "rhr": ("Resting HR vs baseline", "bpm"),
    "sleep": ("Last night's sleep vs goal", "min"),
    "strain": ("Yesterday's strain vs baseline", "min"),
}


def readiness_tile(session: Session, d: date) -> S.Tile:
    """Stored readiness (from pulse.derive) plus a live breakdown of its four parts."""
    tile = daily_tile(session, "readiness", d, fallback_days=1)
    ref = tile.value_date or d
    lo, hi = ref - timedelta(days=derived.BASELINE_DAYS + 2), ref + timedelta(days=1)
    r = derived.readiness(
        ref,
        hrv=daily_values(session, "hrv_rmssd", lo, hi),
        rhr=daily_values(session, "resting_hr", lo, hi),
        sleep_main=daily_values(session, "sleep_main_min", lo, hi),
        strain=daily_values(session, "azm", lo, hi),
        sleep_goal_min=prefs.goals(session)["sleep_min"],
        weights=prefs.readiness_weights(session),
    )
    tile.components = [
        S.ReadinessComponent(
            key=c.key,  # type: ignore[arg-type]
            label=_COMPONENT_META[c.key][0],
            score=c.score,
            weight=round(c.weight, 3),
            value=c.value,
            reference=c.reference,
            unit=_COMPONENT_META[c.key][1],
        )
        for c in r.components
    ]
    tile.formula = derived.READINESS_FORMULA
    tile.note = "Personal heuristic, not a medical measure" + (
        f" · {tile.note}" if tile.note else ""
    )
    if tile.value is None:
        tile.note = "Not enough data yet · personal heuristic"
    return tile


# ---- intraday heart rate -------------------------------------------------------------------


def intraday_heart_rate(session: Session, d: date, zone: ZoneInfo) -> S.IntradayHeartRate:
    points = [
        S.HrPoint(t=ts, avg=round(avg, 1), min=lo, max=hi)
        for ts, avg, lo, hi in session.execute(
            select(IntradayHR.ts_utc, IntradayHR.bpm_avg, IntradayHR.bpm_min, IntradayHR.bpm_max)
            .where(IntradayHR.civil_date == d)
            .order_by(IntradayHR.ts_utc)
        ).all()
    ]
    zone_date = session.execute(
        select(func.max(HrZoneBound.civil_date)).where(HrZoneBound.civil_date <= d)
    ).scalar()
    zones = (
        [
            S.ZoneBand(zone=z, min_bpm=lo, max_bpm=hi)
            for z, lo, hi in session.execute(
                select(HrZoneBound.zone, HrZoneBound.min_bpm, HrZoneBound.max_bpm)
                .where(HrZoneBound.civil_date == zone_date)
                .order_by(HrZoneBound.min_bpm)
            ).all()
        ]
        if zone_date
        else []
    )
    day_start, day_end = CivilWindow(d, d + timedelta(days=1), zone).utc_bounds()
    periods: list[S.Period] = [
        S.Period(
            kind="sleep", start=s.start_utc, end=s.end_utc, label="Sleep" if s.is_main else "Nap"
        )
        for s in session.scalars(
            select(SleepSession).where(
                SleepSession.end_utc > day_start, SleepSession.start_utc < day_end
            )
        )
    ]
    periods += [
        S.Period(
            kind="workout",
            start=e.start_utc,
            end=e.end_utc,
            label=e.name or e.exercise_type.title(),
        )
        for e in session.scalars(
            select(Exercise).where(Exercise.end_utc > day_start, Exercise.start_utc < day_end)
        )
    ]
    resting = daily_values(session, "resting_hr", d, d + timedelta(days=1)).get(d)
    periods.sort(key=lambda p: p.start)
    return S.IntradayHeartRate(
        date=d, points=points, zones=zones, periods=periods, resting_hr=resting
    )


# ---- sleep ---------------------------------------------------------------------------------


def _session_out(session: Session, s: SleepSession, with_stages: bool) -> S.SleepSessionOut:
    stages = (
        [
            S.SleepStageOut(stage=st.stage, start=st.start_utc, end=st.end_utc)
            for st in session.scalars(
                select(SleepStage)
                .where(SleepStage.session_id == s.id)
                .order_by(SleepStage.start_utc)
            )
        ]
        if with_stages
        else []
    )
    return S.SleepSessionOut(
        id=s.id,
        date=s.civil_date,
        start=s.start_utc,
        end=s.end_utc,
        is_main=s.is_main,
        sleep_type=s.sleep_type,
        minutes_in_bed=(s.end_utc - s.start_utc).total_seconds() / 60,
        minutes_asleep=s.minutes_asleep,
        minutes_awake=s.minutes_awake,
        minutes_to_fall_asleep=s.minutes_to_fall_asleep,
        deep_min=s.deep_min,
        light_min=s.light_min,
        rem_min=s.rem_min,
        awake_min=s.awake_min,
        efficiency=s.efficiency,
        stages=stages,
    )


def latest_sleep_date(session: Session) -> date | None:
    return session.execute(select(func.max(SleepSession.civil_date))).scalar()


def sleep_night(session: Session, d: date) -> S.SleepNight:
    sessions = list(session.scalars(select(SleepSession).where(SleepSession.civil_date == d)))
    main = next((s for s in sessions if s.is_main), None) or (
        max(sessions, key=lambda s: s.minutes_asleep) if sessions else None
    )
    naps = [s for s in sessions if s is not main]
    sleeping_hr = None
    if main:
        row = session.execute(
            select(func.avg(IntradayHR.bpm_avg), func.min(IntradayHR.bpm_min)).where(
                IntradayHR.ts_utc >= main.start_utc, IntradayHR.ts_utc < main.end_utc
            )
        ).one()
        if row[0] is not None:
            sleeping_hr = S.SleepingHeartRate(avg=round(row[0], 1), min=row[1])
    day = {
        k: v
        for k, v in session.execute(
            select(DailyMetric.metric, DailyMetric.value).where(DailyMetric.civil_date == d)
        ).all()
    }
    spo2 = (
        S.Spo2(avg=day.get("spo2_avg"), low=day.get("spo2_low"), high=day.get("spo2_high"))
        if "spo2_avg" in day
        else None
    )
    prev_d = session.execute(
        select(func.max(SleepSession.civil_date)).where(SleepSession.civil_date < d)
    ).scalar()
    next_d = session.execute(
        select(func.min(SleepSession.civil_date)).where(SleepSession.civil_date > d)
    ).scalar()
    return S.SleepNight(
        date=d,
        goal_min=prefs.goals(session)["sleep_min"],
        session=_session_out(session, main, True) if main else None,
        naps=[_session_out(session, n, False) for n in naps],
        sleeping_hr=sleeping_hr,
        spo2=spo2,
        skin_temp_delta=day.get("skin_temp_delta"),
        hrv_rmssd=day.get("hrv_rmssd"),
        resting_hr=day.get("resting_hr"),
        prev_date=prev_d,
        next_date=next_d,
    )


_TREND_METRICS = {
    "sleep_min": "asleep_min",
    "sleep_in_bed_min": "in_bed_min",
    "sleep_deep_min": "deep_min",
    "sleep_light_min": "light_min",
    "sleep_rem_min": "rem_min",
    "sleep_awake_min": "awake_min",
    "sleep_efficiency": "efficiency",
    "bedtime_min": "bedtime_min",
    "waketime_min": "waketime_min",
}


def sleep_trend(session: Session, start: date, end_inclusive: date) -> S.SleepTrend:
    rows = session.execute(
        select(DailyMetric.civil_date, DailyMetric.metric, DailyMetric.value).where(
            DailyMetric.metric.in_(list(_TREND_METRICS)),
            DailyMetric.civil_date >= start,
            DailyMetric.civil_date <= end_inclusive,
        )
    ).all()
    by_day: dict[date, dict[str, float]] = defaultdict(dict)
    for d, metric, value in rows:
        by_day[d][_TREND_METRICS[metric]] = value
    nights = [
        S.SleepTrendNight(date=d, **{f: by_day[d].get(f) for f in _TREND_METRICS.values()})
        for d in sorted(by_day)
    ]
    recent = nights[-14:]
    asleep = [n.asleep_min for n in nights if n.asleep_min is not None]
    return S.SleepTrend(
        start=start,
        end=end_inclusive,
        goal_min=prefs.goals(session)["sleep_min"],
        avg_asleep_min=sum(asleep) / len(asleep) if asleep else None,
        consistency=S.SleepConsistency(
            bedtime_sd_min=derived.stdev([n.bedtime_min for n in recent]),
            waketime_sd_min=derived.stdev([n.waketime_min for n in recent]),
            nights=len(recent),
        ),
        nights=nights,
    )


# ---- metrics endpoint ----------------------------------------------------------------------

_BUCKET = {
    "day": "civil_date",
    "week": "date(civil_date, '-6 days', 'weekday 1')",  # Monday on/before the day
    "month": "strftime('%Y-%m-01', civil_date)",
}


def metric_series(
    session: Session, m: Metric, start: date, end_inclusive: date, granularity: S.Granularity
) -> S.MetricSeries:
    agg = "AVG" if granularity == "day" else {"sum": "SUM", "avg": "AVG", "max": "MAX"}[m.agg]
    bucket = _BUCKET[granularity]
    rows = session.execute(
        text(
            f"SELECT {bucket} AS bucket, {agg}(value) FROM daily_metrics "  # noqa: S608 - fixed SQL
            "WHERE metric = :metric AND civil_date >= :lo AND civil_date <= :hi "
            "GROUP BY bucket ORDER BY bucket"
        ),
        {"metric": m.key, "lo": start.isoformat(), "hi": end_inclusive.isoformat()},
    ).all()
    points = [S.DayValue(date=date.fromisoformat(str(b)), value=v) for b, v in rows]
    vals = [p.value for p in points if p.value is not None]
    return S.MetricSeries(
        metric=m.key,
        label=m.label,
        unit=m.unit,
        agg=m.agg,
        granularity=granularity,
        points=points,
        summary=S.SeriesSummary(
            count=len(vals),
            min=min(vals) if vals else None,
            max=max(vals) if vals else None,
            avg=sum(vals) / len(vals) if vals else None,
        ),
    )


# ---- status --------------------------------------------------------------------------------


def metrics_available(session: Session) -> list[S.MetricInfo]:
    rows = session.execute(
        select(
            DailyMetric.metric,
            func.count(),
            func.min(DailyMetric.civil_date),
            func.max(DailyMetric.civil_date),
        ).group_by(DailyMetric.metric)
    ).all()
    out = []
    for key, n, first, last in rows:
        m = CATALOG.get(key)
        if m:
            out.append(
                S.MetricInfo(
                    key=key,
                    label=m.label,
                    unit=m.unit,
                    group=m.group,
                    days=n,
                    first=first,
                    last=last,
                )
            )
    return sorted(out, key=lambda x: (x.group, x.key))


def sync_states(session: Session) -> dict[str, SyncState]:
    return {s.stream: s for s in session.scalars(select(SyncState))}


# ---- phase 2: series, explore, activity, workouts, records ---------------------------------


def metric_band(session: Session, m: Metric, start: date, end_inclusive: date) -> list[S.BandPoint]:
    """Rolling 28-day median/IQR (excluding the day) for every day in the range."""
    values = daily_values(
        session, m.key, start - timedelta(days=derived.BASELINE_DAYS), end_inclusive + timedelta(1)
    )
    out = []
    d = start
    while d <= end_inclusive:
        b = derived.baseline_at(values, d)
        if b is not None:
            out.append(S.BandPoint(date=d, median=b.median, q1=b.q1, q3=b.q3))
        d += timedelta(days=1)
    return out


def weekday_profile(
    session: Session, m: Metric, start: date, end_inclusive: date
) -> S.WeekdayProfile:
    rows = session.execute(
        text(
            "SELECT CAST(strftime('%w', civil_date) AS INTEGER) AS dow, AVG(value), COUNT(*) "
            "FROM daily_metrics WHERE metric = :metric AND civil_date >= :lo "
            "AND civil_date <= :hi GROUP BY dow"
        ),
        {"metric": m.key, "lo": start.isoformat(), "hi": end_inclusive.isoformat()},
    ).all()
    by = {(int(dow) + 6) % 7: (avg, n) for dow, avg, n in rows}  # SQLite 0=Sunday → 0=Monday
    return S.WeekdayProfile(
        metric=m.key,
        label=m.label,
        unit=m.unit,
        start=start,
        end=end_inclusive,
        days=[
            S.WeekdayValue(weekday=i, avg=by.get(i, (None, 0))[0], n=by.get(i, (None, 0))[1])
            for i in range(7)
        ],
    )


def correlate(session: Session, a: str, b: str, start: date, end_inclusive: date) -> S.Correlation:
    xa = daily_values(session, a, start, end_inclusive + timedelta(days=1))
    xb = daily_values(session, b, start, end_inclusive + timedelta(days=1))
    days = sorted(set(xa) & set(xb))
    xs, ys = [xa[d] for d in days], [xb[d] for d in days]
    r = derived.pearson(xs, ys)
    return S.Correlation(
        a=a,
        b=b,
        start=start,
        end=end_inclusive,
        n=len(days),
        r=None if r is None else round(r, 3),
        strength=derived.correlation_strength(r),
        points=[S.PairPoint(date=d, x=x, y=y) for d, x, y in zip(days, xs, ys, strict=True)],
    )


def steps_heatmap(session: Session, start: date, end_inclusive: date, zone: ZoneInfo) -> S.Heatmap:
    """Average steps per (weekday, local hour). The local hour needs DST-aware conversion, so
    this sums 15-minute rows server-side (~35k rows a year)."""
    totals = [[0.0] * 24 for _ in range(7)]
    days: list[set[date]] = [set() for _ in range(7)]
    for d, ts, steps in session.execute(
        select(IntradaySteps.civil_date, IntradaySteps.ts_utc, IntradaySteps.steps).where(
            IntradaySteps.civil_date >= start, IntradaySteps.civil_date <= end_inclusive
        )
    ):
        local = ts.astimezone(zone)
        totals[d.weekday()][local.hour] += steps
        days[d.weekday()].add(d)
    return S.Heatmap(
        start=start,
        end=end_inclusive,
        unit="steps",
        values=[
            [round(v / len(days[w]), 1) if days[w] else None for v in totals[w]] for w in range(7)
        ],
        days=[len(x) for x in days],
    )


def _exercise_out(e: Exercise) -> S.ExerciseOut:
    return S.ExerciseOut(
        id=e.id,
        date=e.civil_date,
        start=e.start_utc,
        end=e.end_utc,
        exercise_type=e.exercise_type,
        name=e.name,
        duration_min=round((e.end_utc - e.start_utc).total_seconds() / 60, 1),
        active_min=None if e.active_s is None else round(e.active_s / 60, 1),
        distance_km=None if e.distance_m is None else round(e.distance_m / 1000, 3),
        steps=e.steps,
        kcal=e.kcal,
        avg_hr=e.avg_hr,
        source=e.source,
    )


def exercises(session: Session, start: date, end_inclusive: date) -> S.ExerciseList:
    rows = session.scalars(
        select(Exercise)
        .where(Exercise.civil_date >= start, Exercise.civil_date <= end_inclusive)
        .order_by(Exercise.start_utc.desc())
    )
    return S.ExerciseList(
        start=start, end=end_inclusive, exercises=[_exercise_out(e) for e in rows]
    )


def exercise_detail(session: Session, exercise_id: str) -> S.ExerciseDetail | None:
    e = session.get(Exercise, exercise_id)
    if e is None:
        return None
    points = [
        S.HrPoint(t=ts, avg=round(avg, 1), min=lo, max=hi)
        for ts, avg, lo, hi in session.execute(
            select(IntradayHR.ts_utc, IntradayHR.bpm_avg, IntradayHR.bpm_min, IntradayHR.bpm_max)
            .where(IntradayHR.ts_utc >= e.start_utc, IntradayHR.ts_utc < e.end_utc)
            .order_by(IntradayHR.ts_utc)
        )
    ]
    zone_date = session.execute(
        select(func.max(HrZoneBound.civil_date)).where(HrZoneBound.civil_date <= e.civil_date)
    ).scalar()
    bounds = (
        {
            z: (lo, hi)
            for z, lo, hi in session.execute(
                select(HrZoneBound.zone, HrZoneBound.min_bpm, HrZoneBound.max_bpm).where(
                    HrZoneBound.civil_date == zone_date
                )
            )
        }
        if zone_date
        else {}
    )
    tiz = derived.time_in_zones([p.avg for p in points], bounds) if points and bounds else {}
    order = ["below", *sorted(bounds, key=lambda z: bounds[z][0])]
    return S.ExerciseDetail(
        exercise=_exercise_out(e),
        points=points,
        zones=[
            S.ZoneBand(zone=z, min_bpm=lo, max_bpm=hi)
            for z, (lo, hi) in sorted(bounds.items(), key=lambda kv: kv[1][0])
        ],
        time_in_zones=[S.ZoneTime(zone=z, minutes=tiz[z]) for z in order if z in tiz],
        max_hr=max((p.max for p in points), default=None),
    )


def _all_values(session: Session, metric: str) -> dict[date, float]:
    return daily_values(session, metric, date(1970, 1, 1), date(9999, 1, 1))


_BESTS: tuple[tuple[str, str, bool], ...] = (
    # (metric, label, lowest)
    ("steps", "Most steps in a day", False),
    ("distance_km", "Longest distance in a day", False),
    ("azm", "Most active zone minutes in a day", False),
    ("calories_active", "Most active calories in a day", False),
    ("sleep_main_min", "Longest main sleep", False),
    ("hrv_rmssd", "Highest HRV", False),
    ("readiness", "Highest readiness", False),
)


def records(session: Session, today: date) -> S.Records:
    goals = prefs.goals(session)
    bests: list[S.RecordOut] = []
    for key, label, lowest in _BESTS:
        b = derived.best(_all_values(session, key), lowest=lowest)
        if b:
            bests.append(
                S.RecordOut(
                    key=key, label=label, unit=CATALOG[key].unit, value=b.value, date=b.date
                )
            )
    rhr = derived.best(derived.rolling_mean(_all_values(session, "resting_hr")), lowest=True)
    if rhr:
        bests.append(
            S.RecordOut(
                key="resting_hr",
                label="Lowest resting HR",
                unit="bpm",
                value=round(rhr.value, 1),
                date=rhr.date,
                note="7-day average, so one odd reading can't set it",
            )
        )
    azm = _all_values(session, "azm")
    weekly = derived.weekly_totals(azm)
    wb = derived.best(weekly)
    if wb:
        bests.append(
            S.RecordOut(
                key="azm_week",
                label="Most active zone minutes in a week",
                unit="min",
                value=wb.value,
                date=wb.date,
                note="Week starting on this Monday",
            )
        )
    longest_workout = session.scalars(
        select(Exercise)
        .where(Exercise.exercise_type != "WALKING")
        .order_by((func.julianday(Exercise.end_utc) - func.julianday(Exercise.start_utc)).desc())
        .limit(1)
    ).first()
    if longest_workout:
        out = _exercise_out(longest_workout)
        bests.append(
            S.RecordOut(
                key="longest_workout",
                label="Longest workout (not walking)",
                unit="min",
                value=out.duration_min,
                date=out.date,
                note=(out.name or out.exercise_type.replace("_", " ").title()),
            )
        )

    def daily_streak(key: str, label: str, metric: str, goal: float) -> S.StreakOut:
        st = derived.streak({d: v >= goal for d, v in _all_values(session, metric).items()}, today)
        return S.StreakOut(
            key=key,
            label=label,
            period="day",
            goal=goal,
            unit=CATALOG[metric].unit,
            current=st.current,
            current_start=st.current_start,
            longest=st.longest,
            longest_end=st.longest_end,
        )

    wk = derived.streak(
        {w: v >= goals["azm_weekly"] for w, v in weekly.items()},
        derived.week_start(today),
        step_days=7,
    )
    streaks = [
        daily_streak("steps", "Step goal", "steps", goals["steps"]),
        daily_streak("sleep", "Sleep goal", "sleep_main_min", goals["sleep_min"]),
        S.StreakOut(
            key="azm",
            label="Weekly AZM goal",
            period="week",
            goal=goals["azm_weekly"],
            unit="min",
            current=wk.current,
            current_start=wk.current_start,
            longest=wk.longest,
            longest_end=wk.longest_end,
        ),
    ]
    return S.Records(as_of=today, bests=bests, streaks=streaks)


# ---- phase 3: daily summary facts ----------------------------------------------------------

_SUMMARY_VITALS = ("resting_hr", "hrv_rmssd", "spo2_avg")
_RECORD_LABELS = {
    "steps": "most steps in a day",
    "distance_km": "longest distance in a day",
    "azm": "most active zone minutes in a day",
    "calories_active": "most active calories in a day",
    "sleep_main_min": "longest main sleep",
    "hrv_rmssd": "highest HRV",
    "readiness": "highest readiness",
}


def _reading(session: Session, metric: str, d: date) -> summary.Reading:
    t = daily_tile(session, metric, d)
    prev = daily_tile(session, metric, d - timedelta(days=1))
    return summary.Reading(
        value=t.value,
        median=t.baseline.median if t.baseline else None,
        status=t.status,
        prev_status=prev.status,
    )


def day_facts(session: Session, d: date, now: datetime, zone: ZoneInfo) -> summary.DayFacts:
    """Everything the summary rules need for civil day ``d`` (today: values so far)."""
    goals = prefs.goals(session)
    is_today = now.astimezone(zone).date() == d
    lo, hi = d - timedelta(days=derived.BASELINE_DAYS + 2), d + timedelta(days=1)
    series = {
        k: daily_values(session, k, lo, hi)
        for k in ("hrv_rmssd", "resting_hr", "sleep_main_min", "azm", "bedtime_min")
    }
    r = derived.readiness(
        d,
        hrv=series["hrv_rmssd"],
        rhr=series["resting_hr"],
        sleep_main=series["sleep_main_min"],
        strain=series["azm"],
        sleep_goal_min=goals["sleep_min"],
        weights=prefs.readiness_weights(session),
    )
    stored = daily_values(session, "readiness", lo, hi)
    rb = derived.baseline_at(stored, d)
    readiness = summary.Reading(
        value=r.score,
        median=rb.median if rb else None,
        status=derived.status(r.score, rb),
    )
    sleep_main = series["sleep_main_min"].get(d)
    bed = series["bedtime_min"]
    usual_bed = [
        derived.clock_wrap(v)
        for v in derived.trailing(bed, d, derived.CONSISTENCY_DAYS, include_day=False)
        if v is not None
    ]
    if is_today:
        st = steps_so_far_tile(session, d, now, zone, goals["steps"])
        steps = summary.Reading(st.value, st.baseline.median if st.baseline else None, st.status)
    else:
        steps = summary.Reading(daily_values(session, "steps", d, hi).get(d))
    azm_week = derived.week_to_date(series["azm"], d)
    rec = records(session, d)
    met_now = {
        "steps": (steps.value or 0) >= goals["steps"],
        "sleep": sleep_main is not None and sleep_main >= goals["sleep_min"],
        "azm": (azm_week or 0) >= goals["azm_weekly"],
    }
    recent = {d, d - timedelta(days=1)} if is_today else {d}
    units = prefs.get(session, "units")
    before = journal.get_journal(session, d - timedelta(days=1)).tags
    evening = {
        t.key: t.label
        for t in session.scalars(select(Tag).where(Tag.key.in_(before), Tag.kind == "evening"))
    }
    return summary.DayFacts(
        date=d,
        is_today=is_today,
        units="imperial" if units == "imperial" else "metric",
        goals=goals,
        readiness=readiness,
        readiness_parts=tuple(
            summary.ReadinessPart(c.key, c.score, c.weight, c.value, c.reference)
            for c in r.components
        ),
        sleep_main_min=sleep_main,
        sleep_debt_min=derived.sleep_debt(series["sleep_main_min"], d, goals["sleep_min"]),
        bedtime_min=bed.get(d),
        bedtime_usual_min=statistics.median(usual_bed) if len(usual_bed) >= 5 else None,
        vitals={k: _reading(session, k, d) for k in _SUMMARY_VITALS}
        | {
            "skin_temp_delta": summary.Reading(
                daily_values(session, "skin_temp_delta", d, hi).get(d)
            )
        },
        steps=steps,
        azm_week=azm_week,
        days_left_in_week=6 - d.weekday(),
        load_ratio=daily_values(session, "load_ratio", d, hi).get(d),
        streaks=tuple(
            summary.StreakFact(s.key, s.current, met_now.get(s.key, False), s.goal)
            for s in rec.streaks
        ),
        records=tuple(
            summary.RecordFact(b.key, _RECORD_LABELS[b.key], b.value, b.unit, b.date)
            for b in rec.bests
            if b.key in _RECORD_LABELS and b.date in recent
        ),
        evening_tags_before=tuple(evening[k] for k in before if k in evening),
    )


def summary_out(session: Session, d: date, now: datetime, zone: ZoneInfo) -> S.Summary:
    out = summary.build_summary(day_facts(session, d, now, zone))
    return S.Summary(
        date=out.date,
        headline=out.headline,
        generated_at=now,
        sentences=[
            S.SummarySentence(text=x.text, tone=x.tone, metrics=list(x.metrics))
            for x in out.sentences
        ],
    )


# ---- phase 4: tags ------------------------------------------------------------------------


def tag_effect_out(
    session: Session,
    tag: Tag,
    m: Metric,
    start: date,
    end_inclusive: date,
    lag: int | None,
    with_points: bool = True,
) -> S.TagEffectOut:
    lag_days = derived.default_lag(m.key, tag.kind) if lag is None else lag
    values = daily_values(session, m.key, start, end_inclusive + timedelta(days=1))
    exclude = journal.tag_days(session, journal.SICK_KEY) if tag.key != journal.SICK_KEY else set()
    tagged, untagged = derived.split_by_tag(
        values, journal.tag_days(session, tag.key), lag_days, exclude
    )
    e = derived.tag_effect(list(tagged.values()), list(untagged.values()))

    def pts(x: dict[date, float]) -> list[S.DayValue]:
        return [S.DayValue(date=d, value=v) for d, v in sorted(x.items())] if with_points else []

    return S.TagEffectOut(
        tag=tag.key,
        tag_label=tag.label,
        metric=m.key,
        metric_label=m.label,
        unit=m.unit,
        lag=lag_days,
        start=start,
        end=end_inclusive,
        n_tagged=e.n_tagged,
        n_untagged=e.n_untagged,
        median_tagged=e.median_tagged,
        median_untagged=e.median_untagged,
        mean_tagged=e.mean_tagged,
        mean_untagged=e.mean_untagged,
        diff=e.diff,
        diff_in_iqr=e.diff_in_iqr,
        p=e.p,
        verdict=e.verdict,
        verdict_text=derived.VERDICT_TEXT[e.verdict],
        tagged=pts(tagged),
        untagged=pts(untagged),
    )


def tag_effects(session: Session, m: Metric, start: date, end_inclusive: date) -> S.TagEffects:
    tags = session.scalars(select(Tag).where(Tag.archived.is_(False)).order_by(Tag.sort))
    effects = [
        tag_effect_out(session, t, m, start, end_inclusive, None, with_points=False) for t in tags
    ]
    effects.sort(key=lambda e: (e.verdict == "too_few", -abs(e.diff_in_iqr or 0.0), e.tag_label))
    return S.TagEffects(metric=m.key, start=start, end=end_inclusive, effects=effects)
