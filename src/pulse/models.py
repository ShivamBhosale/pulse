"""Database schema. All instants are UTC; ``civil_date`` is the America/Toronto (configurable)
calendar day the API assigns to the data, which is what day boundaries follow."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from pulse.db import UtcDateTime


class Base(DeclarativeBase):
    pass


class RawPoint(Base):
    """Every listed/reconciled data point as returned by the API (idempotent upsert)."""

    __tablename__ = "raw_points"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    data_type: Mapped[str] = mapped_column(String(64))
    point_key: Mapped[str] = mapped_column(String(128))
    civil_date: Mapped[date] = mapped_column(Date)
    start_utc: Mapped[datetime | None] = mapped_column(UtcDateTime)
    end_utc: Mapped[datetime | None] = mapped_column(UtcDateTime)
    source: Mapped[str | None] = mapped_column(String(128))
    payload_json: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(UtcDateTime)
    __table_args__ = (
        UniqueConstraint("data_type", "point_key", name="uq_raw_points_type_key"),
        Index("ix_raw_points_type_date", "data_type", "civil_date"),
    )


class DailyMetric(Base):
    """Long-format daily values: one row per (civil_date, metric)."""

    __tablename__ = "daily_metrics"
    civil_date: Mapped[date] = mapped_column(Date, primary_key=True)
    metric: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    __table_args__ = (Index("ix_daily_metrics_metric_date", "metric", "civil_date"),)


class IntradayHR(Base):
    """1-minute heart rate rollups (merged across sources by the API)."""

    __tablename__ = "intraday_hr"
    ts_utc: Mapped[datetime] = mapped_column(UtcDateTime, primary_key=True)
    civil_date: Mapped[date] = mapped_column(Date, index=True)
    bpm_avg: Mapped[float] = mapped_column(Float)
    bpm_min: Mapped[int] = mapped_column(Integer)
    bpm_max: Mapped[int] = mapped_column(Integer)


class IntradaySteps(Base):
    """15-minute step rollups."""

    __tablename__ = "intraday_steps"
    ts_utc: Mapped[datetime] = mapped_column(UtcDateTime, primary_key=True)
    civil_date: Mapped[date] = mapped_column(Date, index=True)
    steps: Mapped[int] = mapped_column(Integer)


class IntradaySample(Base):
    """Sparse instantaneous samples, e.g. SpO2 and HRV RMSSD recorded during sleep."""

    __tablename__ = "intraday_samples"
    metric: Mapped[str] = mapped_column(String(32), primary_key=True)
    ts_utc: Mapped[datetime] = mapped_column(UtcDateTime, primary_key=True)
    civil_date: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)
    __table_args__ = (Index("ix_intraday_samples_metric_date", "metric", "civil_date"),)


class HrZoneBound(Base):
    __tablename__ = "hr_zone_bounds"
    civil_date: Mapped[date] = mapped_column(Date, primary_key=True)
    zone: Mapped[str] = mapped_column(String(16), primary_key=True)
    min_bpm: Mapped[int] = mapped_column(Integer)
    max_bpm: Mapped[int] = mapped_column(Integer)


class SleepSession(Base):
    __tablename__ = "sleep_sessions"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    civil_date: Mapped[date] = mapped_column(Date, index=True)  # local wake date
    start_utc: Mapped[datetime] = mapped_column(UtcDateTime)
    end_utc: Mapped[datetime] = mapped_column(UtcDateTime)
    is_main: Mapped[bool] = mapped_column(Boolean)
    sleep_type: Mapped[str] = mapped_column(String(16))
    minutes_in_period: Mapped[int] = mapped_column(Integer)
    minutes_asleep: Mapped[int] = mapped_column(Integer)
    minutes_awake: Mapped[int] = mapped_column(Integer)
    minutes_to_fall_asleep: Mapped[int] = mapped_column(Integer)
    minutes_after_wake: Mapped[int] = mapped_column(Integer)
    deep_min: Mapped[int | None] = mapped_column(Integer)
    light_min: Mapped[int | None] = mapped_column(Integer)
    rem_min: Mapped[int | None] = mapped_column(Integer)
    awake_min: Mapped[int | None] = mapped_column(Integer)
    efficiency: Mapped[float | None] = mapped_column(Float)
    start_offset_s: Mapped[int] = mapped_column(Integer)  # UTC offset at bedtime
    end_offset_s: Mapped[int] = mapped_column(Integer)  # UTC offset at wake


class SleepStage(Base):
    __tablename__ = "sleep_stages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("sleep_sessions.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[str] = mapped_column(String(16))
    start_utc: Mapped[datetime] = mapped_column(UtcDateTime)
    end_utc: Mapped[datetime] = mapped_column(UtcDateTime)


class Exercise(Base):
    __tablename__ = "exercises"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    civil_date: Mapped[date] = mapped_column(Date, index=True)
    start_utc: Mapped[datetime] = mapped_column(UtcDateTime)
    end_utc: Mapped[datetime] = mapped_column(UtcDateTime)
    exercise_type: Mapped[str] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(128))
    active_s: Mapped[float | None] = mapped_column(Float)
    distance_m: Mapped[float | None] = mapped_column(Float)
    steps: Mapped[int | None] = mapped_column(Integer)
    kcal: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(64))


class SyncState(Base):
    __tablename__ = "sync_state"
    stream: Mapped[str] = mapped_column(String(64), primary_key=True)
    high_water_mark: Mapped[date | None] = mapped_column(Date)
    backfill_cursor: Mapped[date | None] = mapped_column(Date)
    backfill_floor: Mapped[date | None] = mapped_column(Date)
    last_success: Mapped[datetime | None] = mapped_column(UtcDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(UtcDateTime)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text)


# ---- journal: tags and notes you enter yourself (never touched by sync) ---------------------


class Tag(Base):
    __tablename__ = "tags"
    key: Mapped[str] = mapped_column(String(48), primary_key=True)
    label: Mapped[str] = mapped_column(String(48))
    # evening: affects the following night (compared with next day's overnight metrics)
    kind: Mapped[str] = mapped_column(String(16))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)


class DayTag(Base):
    __tablename__ = "day_tags"
    civil_date: Mapped[date] = mapped_column(Date, primary_key=True)
    tag_key: Mapped[str] = mapped_column(
        String(48), ForeignKey("tags.key", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    __table_args__ = (Index("ix_day_tags_tag", "tag_key"),)


class DayNote(Base):
    __tablename__ = "day_notes"
    civil_date: Mapped[date] = mapped_column(Date, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)
