"""Persist collection evidence and story membership.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("news_items", sa.Column("story_id", sa.String(36), nullable=True))
    op.add_column("news_items", sa.Column("collection_info", sa.JSON(), nullable=True))
    op.create_index("ix_news_items_story_id", "news_items", ["story_id"])
    op.create_index("ix_news_items_created_at", "news_items", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_news_items_created_at", table_name="news_items")
    op.drop_index("ix_news_items_story_id", table_name="news_items")
    op.drop_column("news_items", "collection_info")
    op.drop_column("news_items", "story_id")
