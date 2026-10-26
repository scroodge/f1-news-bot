"""Append-only editorial feedback and source/draft snapshots.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "editorial_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        # No cascading FK: snapshots survive ordinary removal from the news queue.
        sa.Column("news_id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.String(36), nullable=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("actor", sa.JSON(), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("recommendation", sa.JSON(), nullable=False),
        sa.Column("versions", sa.JSON(), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("draft_hash", sa.String(64), nullable=False),
        sa.Column("training_eligible", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_editorial_events_news_created", "editorial_events", ["news_id", "created_at"]
    )
    op.create_index("ix_editorial_events_created", "editorial_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_editorial_events_created", table_name="editorial_events")
    op.drop_index("ix_editorial_events_news_created", table_name="editorial_events")
    op.drop_table("editorial_events")
