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


class Today(BaseModel):
    date: Day
    generated_at: Instant
    last_synced: Instant | None
    goals: Goals
    tiles: list[Tile]
    heart_rate: IntradayHeartRate
    steps_curve: StepsCurve


class SeriesSummary(BaseModel):
    count: int
    min: float | None
    max: float | None
    avg: float | None


class MetricSeries(BaseModel):
    metric: str
    label: str
    unit: str
    agg: Literal["sum", "avg"]
    granularity: Granularity
    points: list[DayValue]
    summary: SeriesSummary


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


class Status(BaseModel):
    auth: AuthStatus
    last_sync: Instant | None
    next_run: Instant | None
    syncing: bool
    streams: list[StreamStatus]
    backfill: BackfillStatus
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


class Health(BaseModel):
    status: str
    version: str
