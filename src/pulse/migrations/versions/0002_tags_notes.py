"""tags and notes (journal)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-22
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

import pulse.db

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TAGS = (
    # key, label, kind
    ("alcohol", "Alcohol", "evening"),
    ("late-meal", "Late meal", "evening"),
    ("late-caffeine", "Late caffeine", "evening"),
    ("screen-late", "Screen late", "evening"),
    ("sick", "Sick", "day"),
    ("travel", "Travel", "day"),
    ("stress", "Stress", "day"),
    ("rest-day", "Rest day", "day"),
)


def upgrade() -> None:
    tags = op.create_table(
        "tags",
        sa.Column("key", sa.String(length=48), nullable=False),
        sa.Column("label", sa.String(length=48), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("created_at", pulse.db.UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "day_notes",
        sa.Column("civil_date", sa.Date(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("updated_at", pulse.db.UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("civil_date"),
    )
    op.create_table(
        "day_tags",
        sa.Column("civil_date", sa.Date(), nullable=False),
        sa.Column("tag_key", sa.String(length=48), nullable=False),
        sa.Column("created_at", pulse.db.UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tag_key"], ["tags.key"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("civil_date", "tag_key"),
    )
    with op.batch_alter_table("day_tags", schema=None) as batch_op:
        batch_op.create_index("ix_day_tags_tag", ["tag_key"], unique=False)
    now = datetime.now(UTC)
    op.bulk_insert(
        tags,
        [
            {
                "key": k,
                "label": label,
                "kind": kind,
                "archived": False,
                "sort": i,
                "created_at": now,
            }
            for i, (k, label, kind) in enumerate(DEFAULT_TAGS)
        ],
    )


def downgrade() -> None:
    with op.batch_alter_table("day_tags", schema=None) as batch_op:
        batch_op.drop_index("ix_day_tags_tag")
    op.drop_table("day_tags")
    op.drop_table("day_notes")
    op.drop_table("tags")
