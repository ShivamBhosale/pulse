"""Replace a stream's rows for a civil-date window, atomically."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Table, delete, or_
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from pulse.models import Base
from pulse.sync.parsers import Batch
from pulse.sync.streams import Clear, Stream

# Insert order matters for foreign keys.
TABLE_ORDER = (
    "raw_points",
    "daily_metrics",
    "intraday_hr",
    "intraday_steps",
    "intraday_samples",
    "hr_zone_bounds",
    "sleep_sessions",
    "sleep_stages",
    "exercises",
)
# Conflict targets for upserts (primary keys, or the natural unique key).
CONFLICT_KEYS: dict[str, tuple[str, ...] | None] = {
    "raw_points": ("data_type", "point_key"),
    "daily_metrics": ("civil_date", "metric"),
    "intraday_hr": ("ts_utc",),
    "intraday_steps": ("ts_utc",),
    "intraday_samples": ("metric", "ts_utc"),
    "hr_zone_bounds": ("civil_date", "zone"),
    "sleep_sessions": ("id",),
    "sleep_stages": None,  # surrogate id; replaced per session instead
    "exercises": ("id",),
}
INSERT_CHUNK = 2000


def _table(name: str) -> Table:
    return Base.metadata.tables[name]


def _clear(session: Session, clear: Clear, start: date, end: date) -> int:
    t = _table(clear.table)
    stmt = delete(t).where(t.c.civil_date >= start, t.c.civil_date < end)
    if clear.column and clear.values:
        col = t.c[clear.column]
        exact = [v for v in clear.values if not v.endswith("*")]
        prefixes = [v[:-1] for v in clear.values if v.endswith("*")]
        conds = ([col.in_(exact)] if exact else []) + [col.like(f"{p}%") for p in prefixes]
        stmt = stmt.where(or_(*conds))
    return session.execute(stmt).rowcount or 0  # type: ignore[attr-defined]


def _upsert(session: Session, name: str, rows: list[dict[str, Any]]) -> None:
    t = _table(name)
    keys = CONFLICT_KEYS[name]
    for i in range(0, len(rows), INSERT_CHUNK):
        chunk = rows[i : i + INSERT_CHUNK]
        stmt = insert(t)
        if keys:
            update_cols = {
                c.name: stmt.excluded[c.name]
                for c in t.columns
                if c.name not in keys and not c.primary_key
            }
            stmt = stmt.on_conflict_do_update(index_elements=list(keys), set_=update_cols)
        session.execute(stmt, chunk)


def write_window(session: Session, stream: Stream, start: date, end: date, batch: Batch) -> int:
    """Delete everything ``stream`` owns in [start, end), then upsert ``batch``.
    Returns the number of rows written. Caller commits."""
    for clear in stream.owns:
        _clear(session, clear, start, end)
    # Sessions re-fetched from outside the window (upserted, not deleted) need fresh stages.
    session_ids = [r["id"] for r in batch.rows.get("sleep_sessions", [])]
    if session_ids:
        st = _table("sleep_stages")
        session.execute(delete(st).where(st.c.session_id.in_(session_ids)))
    written = 0
    for name in TABLE_ORDER:
        rows = batch.rows.get(name)
        if rows:
            _upsert(session, name, rows)
            written += len(rows)
    return written
