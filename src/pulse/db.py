"""SQLite engine (WAL), sessions and migrations."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, Engine, create_engine, event
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class UtcDateTime(TypeDecorator[datetime]):
    """Stores aware datetimes as naive UTC; always returns aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime passed to UtcDateTime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


def _set_pragmas(dbapi_conn: Any, _record: Any) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.close()


def make_engine(path: Path | None) -> Engine:
    """File-backed engine, or a shared in-memory engine when ``path`` is None (tests)."""
    if path is None:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 30}
        )
    event.listen(engine, "connect", _set_pragmas)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def migrate(engine: Engine) -> None:
    """Upgrade the schema to the latest Alembic revision."""
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
