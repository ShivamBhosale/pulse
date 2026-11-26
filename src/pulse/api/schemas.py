"""API response/request models (also the OpenAPI contract for the future Android client)."""

from __future__ import annotations

from datetime import date as Day
from datetime import datetime as Instant
from typing import Literal

from pydantic import BaseModel, Field

StatusLevel = Literal["in_range", "mild", "notable", "none"]
Granularity = Literal["day", "week", "month"]


class DayValue(BaseModel):
    date: Day
    value: float | None


class BaselineOut(BaseModel):
    median: float
    q1: float
    q3: float
    n: int


class Goals(BaseModel):
    sleep_min: int
    steps: int
    azm_weekly: int


class ReadinessComponent(BaseModel):
    key: Literal["hrv", "rhr", "sleep", "strain"]
    label: str
    score: float | None = Field(description="0-100, null when the input is missing")
    weight: float = Field(description="Effective weight after renormalising missing parts")
    value: float | None
    reference: float | None = Field(description="Baseline median, or the goal for sleep")
    unit: str


class Tile(BaseModel):
    key: str
    label: str
    unit: str
    value: float | None
    value_date: Day | None = Field(description="Day the value belongs to (may be yesterday)")
    delta: float | None = Field(description="value minus baseline median")
    status: StatusLevel
    better: Literal["up", "down", "none"]
    baseline: BaselineOut | None
    spark: list[DayValue]
    note: str | None = None
    goal: float | None = None
    components: list[ReadinessComponent] | None = None
    formula: str | None = None


class HrPoint(BaseModel):
    t: Instant
    avg: float
    min: int
    max: int


class ZoneBand(BaseModel):
    zone: str
    min_bpm: int
    max_bpm: int


class Period(BaseModel):
    kind: Literal["sleep", "workout"]
    start: Instant
    end: Instant
    label: str


class IntradayHeartRate(BaseModel):
    date: Day
    points: list[HrPoint]
    zones: list[ZoneBand]
    periods: list[Period]
    resting_hr: float | None


class StepsCurve(BaseModel):
    slot_minutes: int = 15
    today: list[float | None] = Field(description="Cumulative steps per slot; null after now")
    median: list[float] = Field(description="Median cumulative curve of the previous 28 days")
    days_in_median: int


class SummarySentence(BaseModel):
    text: str
    tone: Literal["good", "neutral", "attention"]
    metrics: list[str] = Field(description="Metric keys the sentence is about (for linking)")


class Summary(BaseModel):
    date: Day
    headline: str
    sentences: list[SummarySentence]
    generated_at: Instant


class Today(BaseModel):
    date: Day
    generated_at: Instant
    last_synced: Instant | None
    goals: Goals
    tiles: list[Tile]
    heart_rate: IntradayHeartRate
    steps_curve: StepsCurve
    summary: Summary


class SeriesSummary(BaseModel):
    count: int
    min: float | None
    max: float | None
    avg: float | None


class BandPoint(BaseModel):
    date: Day
    median: float
    q1: float
    q3: float


class MetricSeries(BaseModel):
    metric: str
    label: str
    unit: str
    agg: Literal["sum", "avg", "max"]
    granularity: Granularity
    points: list[DayValue]
    summary: SeriesSummary
    band: list[BandPoint] | None = Field(
        default=None, description="Rolling 28-day median/IQR per day (day granularity only)"
    )


class MultiSeries(BaseModel):
    start: Day
    end: Day
    granularity: Granularity
    series: list[MetricSeries]


class WeekdayValue(BaseModel):
    weekday: int = Field(description="0 = Monday")
    avg: float | None
    n: int


class WeekdayProfile(BaseModel):
    metric: str
    label: str
    unit: str
    start: Day
    end: Day
    days: list[WeekdayValue]


class PairPoint(BaseModel):
    date: Day
    x: float
    y: float


class Correlation(BaseModel):
    a: str
    b: str
    start: Day
    end: Day
    n: int
    r: float | None
    strength: str
    points: list[PairPoint]


class Heatmap(BaseModel):
    start: Day
    end: Day
    unit: str
    values: list[list[float | None]] = Field(
        description="7 rows (Monday first) x 24 hours: average steps in that hour"
    )
    days: list[int] = Field(description="Days with data per weekday row")


class ExerciseOut(BaseModel):
    id: str
    date: Day
    start: Instant
    end: Instant
    exercise_type: str
    name: str | None
    duration_min: float
    active_min: float | None
    distance_km: float | None
    steps: int | None
    kcal: float | None
    avg_hr: float | None
    source: str


class ExerciseList(BaseModel):
    start: Day
    end: Day
    exercises: list[ExerciseOut]


class ZoneTime(BaseModel):
    zone: str
    minutes: int


class ExerciseDetail(BaseModel):
    exercise: ExerciseOut
    points: list[HrPoint]
    zones: list[ZoneBand]
    time_in_zones: list[ZoneTime]
    max_hr: int | None


class RecordOut(BaseModel):
    key: str
    label: str
    unit: str
    value: float
    date: Day
    note: str | None = None


class StreakOut(BaseModel):
    key: str
    label: str
    period: Literal["day", "week"]
    goal: float
    unit: str
    current: int
    current_start: Day | None
    longest: int
    longest_end: Day | None


class Records(BaseModel):
    as_of: Day
    bests: list[RecordOut]
    streaks: list[StreakOut]


class ReadinessWeights(BaseModel):
    hrv: float = Field(ge=0, le=100)
    rhr: float = Field(ge=0, le=100)
    sleep: float = Field(ge=0, le=100)
    strain: float = Field(ge=0, le=100)


class SettingsOut(BaseModel):
    goals: Goals
    units: Literal["metric", "imperial"]
    readiness_weights: ReadinessWeights
    readiness_formula: str
    passcode_set: bool


class GoalsIn(BaseModel):
    sleep_min: int = Field(ge=180, le=720)
    steps: int = Field(ge=1000, le=50000)
    azm_weekly: int = Field(ge=10, le=1500)


class SettingsIn(BaseModel):
    goals: GoalsIn | None = None
    units: Literal["metric", "imperial"] | None = None
    readiness_weights: ReadinessWeights | None = None


class PasscodeChange(BaseModel):
    current: str | None = Field(default=None, pattern=r"^\d{4,6}$")
    new: str | None = Field(
        default=None, pattern=r"^\d{4,6}$", description="null clears the passcode"
    )


class BackfillIn(BaseModel):
    since: Day | None = Field(default=None, description="Default: discover earliest data")


class ResyncIn(BaseModel):
    since: Day
    until: Day | None = Field(default=None, description="Inclusive; default today")
    streams: list[str] | None = Field(default=None, description="Default: every stream")


class JobAccepted(BaseModel):
    status: Literal["started"]
    job: str


class MetricInfo(BaseModel):
    key: str
    label: str
    unit: str
    group: str
    days: int
    first: Day
    last: Day


class StreamStatus(BaseModel):
    stream: str
    high_water_mark: Day | None
    last_success: Instant | None
    last_error: str | None
    last_error_at: Instant | None


class AuthStatus(BaseModel):
    ok: bool
    error: str | None
    checked_at: Instant | None


class BackfillStatus(BaseModel):
    floor: Day | None
    cursor: Day | None
    last_success: Instant | None
    last_error: str | None


class BackupStatus(BaseModel):
    enabled: bool
    schedule: str = Field(description="Local time of the nightly backup, HH:MM")
    next_run: Instant | None
    running: bool
    last_at: Instant | None
    last_error: str | None
    last_error_at: Instant | None
    latest_file: str | None
    latest_size_bytes: int | None
    count: int
    total_bytes: int


class Status(BaseModel):
    auth: AuthStatus
    last_sync: Instant | None
    next_run: Instant | None
    syncing: bool
    job: str | None = Field(default=None, description="sync | backfill | resync while running")
    stream_names: list[str] = []
    streams: list[StreamStatus]
    backfill: BackfillStatus
    backup: BackupStatus
    metrics: list[MetricInfo]


class SleepStageOut(BaseModel):
    stage: str
    start: Instant
    end: Instant


class SleepSessionOut(BaseModel):
    id: str
    date: Day
    start: Instant
    end: Instant
    is_main: bool
    sleep_type: str
    minutes_in_bed: float
    minutes_asleep: int
    minutes_awake: int
    minutes_to_fall_asleep: int
    deep_min: int | None
    light_min: int | None
    rem_min: int | None
    awake_min: int | None
    efficiency: float | None
    stages: list[SleepStageOut]


class SleepingHeartRate(BaseModel):
    avg: float
    min: int


class Spo2(BaseModel):
    avg: float | None
    low: float | None
    high: float | None


class SleepNight(BaseModel):
    date: Day
    goal_min: int
    session: SleepSessionOut | None
    naps: list[SleepSessionOut]
    sleeping_hr: SleepingHeartRate | None
    spo2: Spo2 | None
    skin_temp_delta: float | None
    hrv_rmssd: float | None
    resting_hr: float | None
    prev_date: Day | None
    next_date: Day | None


class SleepTrendNight(BaseModel):
    date: Day
    asleep_min: float | None
    in_bed_min: float | None
    deep_min: float | None
    light_min: float | None
    rem_min: float | None
    awake_min: float | None
    efficiency: float | None
    bedtime_min: float | None = Field(description="Minutes from local midnight of wake day")
    waketime_min: float | None


class SleepConsistency(BaseModel):
    bedtime_sd_min: float | None
    waketime_sd_min: float | None
    nights: int


class SleepTrend(BaseModel):
    start: Day
    end: Day
    goal_min: int
    avg_asleep_min: float | None
    consistency: SleepConsistency
    nights: list[SleepTrendNight]


class SyncAccepted(BaseModel):
    status: Literal["started", "already_running"]


class SessionState(BaseModel):
    passcode_required: bool
    authenticated: bool


class PasscodeIn(BaseModel):
    passcode: str = Field(pattern=r"^\d{4,6}$")


TagKind = Literal["evening", "day"]


class TagOut(BaseModel):
    key: str
    label: str
    kind: TagKind = Field(description="evening: affects the following night")
    archived: bool
    uses: int
    last_used: Day | None


class TagIn(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    kind: TagKind = "day"


class TagPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=40)
    kind: TagKind | None = None
    archived: bool | None = None


class Journal(BaseModel):
    date: Day
    tags: list[str]
    note: str


class JournalIn(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=30)
    note: str = Field(default="", max_length=2000)


class JournalRange(BaseModel):
    start: Day
    end: Day
    days: list[Journal]


class TagEffectOut(BaseModel):
    tag: str
    tag_label: str
    metric: str
    metric_label: str
    unit: str
    lag: int = Field(description="Metric day = tag day + lag (1 = the following night)")
    start: Day
    end: Day
    n_tagged: int
    n_untagged: int
    median_tagged: float | None
    median_untagged: float | None
    mean_tagged: float | None
    mean_untagged: float | None
    diff: float | None = Field(description="Median tagged minus median untagged")
    diff_in_iqr: float | None = Field(description="diff divided by the untagged IQR")
    p: float | None = Field(description="Permutation test p-value (two-sided)")
    verdict: Literal["clear", "possible", "none", "too_few"]
    verdict_text: str
    tagged: list[DayValue] = []
    untagged: list[DayValue] = []


class TagEffects(BaseModel):
    metric: str
    start: Day
    end: Day
    effects: list[TagEffectOut]


CellState = Literal["ok", "low", "missing", "untracked", "today"]
FreshStatus = Literal["fresh", "behind", "stale", "none"]


class GapOut(BaseModel):
    start: Day
    end: Day = Field(description="Inclusive")
    days: int


class SignalCoverage(BaseModel):
    key: str
    label: str
    stream: str = Field(description="Sync stream that fetches this signal (for re-sync)")
    first: Day | None = Field(description="First day this signal ever had data")
    present_days: int
    expected_days: int = Field(description="Days in range since first data, excluding today")
    longest_gap: int
    current_gap: int = Field(description="Missing days up to yesterday (0 = up to date)")
    gaps: list[GapOut] = Field(description="Newest first, at most 50")
    cells: list[CellState] = Field(description="One per day in `days`")
    values: list[float | None] = Field(description="Wear fraction 0-1 (wear only)")


class Coverage(BaseModel):
    start: Day
    end: Day
    days: list[Day]
    signals: list[SignalCoverage]


class FreshItem(BaseModel):
    key: str
    label: str
    latest_at: Instant | None = Field(description="Newest data instant (intraday signals)")
    latest_date: Day | None = Field(description="Newest day with data")
    lag_min: float | None
    status: FreshStatus


class DataFreshness(BaseModel):
    now: Instant
    band: FreshItem = Field(description="Newest heart-rate minute: when the band last synced")
    signals: list[FreshItem]
    streams: list[StreamStatus]
    last_sync: Instant | None
    next_run: Instant | None
    job: str | None


class WearGapOut(BaseModel):
    start: Instant
    end: Instant
    minutes: int


class DayHealth(BaseModel):
    date: Day
    wear_fraction: float | None
    wear_minutes: int
    day_minutes: int
    wear_gaps: list[WearGapOut]
    step_slots: int
    signals: dict[str, CellState]


class WidgetReadiness(BaseModel):
    value: float | None
    status: StatusLevel
    label: str = Field(description="e.g. 'a bit above your usual'")


class WidgetSnapshot(BaseModel):
    """Compact payload for the Android home-screen widget (a few hundred bytes)."""

    date: Day
    generated_at: Instant
    readiness: WidgetReadiness
    steps: float | None
    steps_goal: int
    steps_status: StatusLevel
    sleep_main_min: float | None
    sleep_goal_min: int
    azm_week: float | None
    azm_goal: int
    last_synced: Instant | None
    auth_ok: bool


class Health(BaseModel):
    status: str
    version: str
