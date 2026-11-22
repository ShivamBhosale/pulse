"""Alembic environment: uses the connection handed over by ``pulse.db.migrate``."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from pulse.models import Base

config = context.config
target_metadata = Base.metadata


def run() -> None:
    connection = config.attributes.get("connection")
    if connection is None:  # `alembic` CLI usage (development only)
        engine = engine_from_config(
            config.get_section(config.config_ini_section) or {},
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with engine.connect() as conn:
            _configure_and_run(conn)
    else:
        _configure_and_run(connection)


def _configure_and_run(connection: object) -> None:
    context.configure(
        connection=connection,  # type: ignore[arg-type]
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite ALTER support
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


run()
