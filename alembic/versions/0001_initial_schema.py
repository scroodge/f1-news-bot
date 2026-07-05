"""Initial schema: single news_items table with status lifecycle

Replaces the pre-rebuild two-table layout (news_items + published_news_items,
boolean processed/published flags). Those tables only ever existed empty on
the fresh Contabo DB, so upgrade drops them unconditionally if present.

Revision ID: 0001
Revises:
Create Date: 2026-07-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEWS_STATUS = sa.Enum(
    "collected",
    "processed",
    "queued",
    "published",
    "rejected",
    name="newsstatus",
    native_enum=False,
)


def upgrade() -> None:
    # Drop pre-rebuild tables (created empty by the old create_all on the fresh DB)
    op.execute("DROP TABLE IF EXISTS published_news_items")
    op.execute("DROP TABLE IF EXISTS news_items")

    op.create_table(
        "news_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("url", sa.String(), nullable=False, unique=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("keywords", sa.JSON(), nullable=True),
        sa.Column("status", NEWS_STATUS, nullable=False, server_default="collected"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        # media
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("video_url", sa.String(), nullable=True),
        sa.Column("media_type", sa.String(), nullable=True),
        # processed
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("key_points", sa.JSON(), nullable=True),
        sa.Column("sentiment", sa.String(), nullable=False, server_default="neutral"),
        sa.Column("importance_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("formatted_content", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        # translations
        sa.Column("translated_title", sa.Text(), nullable=True),
        sa.Column("translated_summary", sa.Text(), nullable=True),
        sa.Column("translated_key_points", sa.JSON(), nullable=True),
        sa.Column("original_language", sa.String(), nullable=True),
        # moderation / publication
        sa.Column("rejected_reason", sa.String(), nullable=True),
        sa.Column("moderated_at", sa.DateTime(), nullable=True),
        sa.Column("telegram_message_id", sa.Integer(), nullable=True),
        sa.Column("published_to_channel_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_news_items_status", "news_items", ["status"])


def downgrade() -> None:
    op.drop_index("ix_news_items_status", table_name="news_items")
    op.drop_table("news_items")
