"""Read-side queries for the API. Aggregation happens in SQL or small server-side loops,
never in the browser."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from pulse import derived, prefs
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


def readiness_placeholder(d: date) -> S.Tile:
    return S.Tile(
        key="readiness",
        label="Readiness",
        unit="score",
        value=None,
        value_date=None,
        delta=None,
        status="none",
        better="up",
        baseline=None,
        spark=spark({}, d),
        note="Personal heuristic — arrives in phase 2",
    )


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
    agg = "SUM" if m.agg == "sum" and granularity != "day" else "AVG"
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
