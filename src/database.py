"""
Async database layer for F1 News Bot.

One table, one source of truth: `news_items` moves through NewsStatus
(collected -> processed -> queued -> published / rejected). Schema is managed
by Alembic (see alembic/); `create_tables()` exists for tests only.
"""

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    Uuid,
    func,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import settings
from .models import NewsItem, NewsStatus, ProcessedNewsItem, SourceType, Stats
from .utils.timezone import to_naive_utc

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class NewsItemDB(Base):
    """News item — one row for the whole lifecycle"""

    __tablename__ = "news_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[NewsStatus] = mapped_column(
        Enum(NewsStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        default=NewsStatus.COLLECTED,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Media fields
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    video_url: Mapped[str | None] = mapped_column(String, nullable=True)
    media_type: Mapped[str | None] = mapped_column(String, nullable=True)

    # Processed fields
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_points: Mapped[list] = mapped_column(JSON, default=list)
    sentiment: Mapped[str] = mapped_column(String, default="neutral")
    importance_level: Mapped[int] = mapped_column(Integer, default=1)
    formatted_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)

    # Translated content fields
    translated_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    translated_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    translated_key_points: Mapped[list] = mapped_column(JSON, default=list)
    original_language: Mapped[str | None] = mapped_column(String, nullable=True)

    # Moderation / publication metadata
    rejected_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published_to_channel_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Semantic dedup (bge-m3 vector as JSON; scale doesn't warrant pgvector)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # LLM token usage tracking
    llm_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)


def _to_model(item: NewsItemDB) -> ProcessedNewsItem | NewsItem:
    """Convert a DB row to the appropriate pydantic model"""
    base = {
        "id": str(item.id),
        "title": item.title,
        "content": item.content,
        "url": item.url,
        "source": item.source,
        "source_type": SourceType(item.source_type),
        "published_at": item.published_at,
        "relevance_score": item.relevance_score,
        "keywords": item.keywords or [],
        "status": NewsStatus(item.status),
        "created_at": item.created_at,
        "image_url": item.image_url,
        "video_url": item.video_url,
        "media_type": item.media_type,
    }
    if item.status == NewsStatus.COLLECTED:
        return NewsItem(**base)
    return ProcessedNewsItem(
        **base,
        summary=item.summary or "",
        key_points=item.key_points or [],
        sentiment=item.sentiment or "neutral",
        importance_level=item.importance_level or 1,
        formatted_content=item.formatted_content or "",
        tags=item.tags or [],
        translated_title=item.translated_title,
        translated_summary=item.translated_summary,
        translated_key_points=item.translated_key_points or [],
        original_language=item.original_language,
        llm_usage=item.llm_usage,
        rejected_reason=item.rejected_reason,
        telegram_message_id=item.telegram_message_id,
        published_to_channel_at=item.published_to_channel_at,
    )


class DatabaseManager:
    """Async database operations manager"""

    def __init__(self, database_url: str | None = None):
        self.engine = create_async_engine(database_url or settings.database_url_async)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> AsyncSession:
        return self.session_factory()

    async def create_tables(self):
        """Create tables directly — for tests; production schema is Alembic's job"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self):
        await self.engine.dispose()

    async def ping(self) -> bool:
        try:
            async with self.session() as s:
                await s.execute(select(1))
            return True
        except Exception as e:
            logger.error(f"Database ping failed: {e}")
            return False

    # --- writes -----------------------------------------------------------

    async def save_news_item(self, news_item: NewsItem) -> str | None:
        """Insert a collected item. Returns id, or None when the URL already exists."""
        async with self.session() as s:
            db_item = NewsItemDB(
                title=news_item.title,
                content=news_item.content,
                url=news_item.url,
                source=news_item.source,
                source_type=news_item.source_type.value,
                published_at=to_naive_utc(news_item.published_at),
                relevance_score=news_item.relevance_score,
                keywords=news_item.keywords,
                status=NewsStatus.COLLECTED,
                image_url=news_item.image_url,
                video_url=news_item.video_url,
                media_type=news_item.media_type,
            )
            s.add(db_item)
            try:
                await s.commit()
            except IntegrityError:
                await s.rollback()
                return None
            return str(db_item.id)

    async def mark_processed(
        self, news_id: str, processed: ProcessedNewsItem, llm_usage: dict | None = None
    ) -> bool:
        """Attach AI results and move collected -> processed (or re-process)"""
        async with self.session() as s:
            item = await s.get(NewsItemDB, uuid.UUID(news_id))
            if not item:
                return False
            item.summary = processed.summary
            item.key_points = processed.key_points
            item.sentiment = processed.sentiment
            item.importance_level = processed.importance_level
            item.formatted_content = processed.formatted_content
            item.tags = processed.tags
            item.translated_title = processed.translated_title
            item.translated_summary = processed.translated_summary
            item.translated_key_points = processed.translated_key_points
            item.original_language = processed.original_language
            item.status = NewsStatus.PROCESSED
            if llm_usage is not None:
                item.llm_usage = llm_usage
            await s.commit()
            return True

    async def approve(self, news_id: str) -> bool:
        """Admin approved: processed -> queued"""
        return await self._transition(
            news_id, from_statuses={NewsStatus.PROCESSED}, to_status=NewsStatus.QUEUED
        )

    async def reject(self, news_id: str, reason: str | None = None) -> bool:
        """Rules or admin rejected: collected/processed/queued -> rejected"""
        async with self.session() as s:
            item = await s.get(NewsItemDB, uuid.UUID(news_id))
            if not item or item.status == NewsStatus.PUBLISHED:
                return False
            item.status = NewsStatus.REJECTED
            item.rejected_reason = reason
            item.moderated_at = datetime.utcnow()
            await s.commit()
            return True

    async def mark_published(self, news_id: str, telegram_message_id: int | None = None) -> bool:
        """Publisher done: queued -> published"""
        async with self.session() as s:
            item = await s.get(NewsItemDB, uuid.UUID(news_id))
            if not item:
                return False
            item.status = NewsStatus.PUBLISHED
            item.telegram_message_id = telegram_message_id
            item.published_to_channel_at = datetime.utcnow()
            await s.commit()
            return True

    async def _transition(self, news_id: str, from_statuses: set, to_status: NewsStatus) -> bool:
        async with self.session() as s:
            item = await s.get(NewsItemDB, uuid.UUID(news_id))
            if not item or NewsStatus(item.status) not in from_statuses:
                return False
            item.status = to_status
            item.moderated_at = datetime.utcnow()
            await s.commit()
            return True

    async def update_fields(self, news_id: str, **fields) -> bool:
        """Update editable content fields (title, summary, ...)"""
        allowed = {
            "title",
            "summary",
            "formatted_content",
            "tags",
            "importance_level",
            "translated_title",
            "translated_summary",
            "key_points",
            "llm_usage",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Fields not editable: {unknown}")
        async with self.session() as s:
            item = await s.get(NewsItemDB, uuid.UUID(news_id))
            if not item:
                return False
            for key, value in fields.items():
                setattr(item, key, value)
            await s.commit()
            return True

    async def set_embedding(self, news_id: str, embedding: list[float]) -> bool:
        async with self.session() as s:
            item = await s.get(NewsItemDB, uuid.UUID(news_id))
            if not item:
                return False
            item.embedding = embedding
            await s.commit()
            return True

    async def get_recent_embeddings(
        self, days: int = 7, exclude_id: str | None = None
    ) -> list[tuple[str, list[float]]]:
        """(id, embedding) pairs of recent non-rejected items, for dedup"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        async with self.session() as s:
            query = select(NewsItemDB.id, NewsItemDB.embedding).where(
                NewsItemDB.created_at >= cutoff,
                NewsItemDB.embedding.is_not(None),
                NewsItemDB.status != NewsStatus.REJECTED,
            )
            if exclude_id:
                query = query.where(NewsItemDB.id != uuid.UUID(exclude_id))
            result = await s.execute(query)
            return [(str(item_id), embedding) for item_id, embedding in result.all()]

    async def delete_item(self, news_id: str) -> bool:
        async with self.session() as s:
            item = await s.get(NewsItemDB, uuid.UUID(news_id))
            if not item:
                return False
            await s.delete(item)
            await s.commit()
            logger.info(f"Deleted news item {news_id}")
            return True

    async def reject_all_pending(self) -> int:
        """Reject everything awaiting moderation (PROCESSED). Returns count."""
        async with self.session() as s:
            result = await s.execute(
                select(NewsItemDB).where(NewsItemDB.status == NewsStatus.PROCESSED)
            )
            items = result.scalars().all()
            for item in items:
                item.status = NewsStatus.REJECTED
                item.rejected_reason = "bulk-rejected by admin"
                item.moderated_at = datetime.utcnow()
            await s.commit()
            return len(items)

    async def reject_all_collected(self) -> int:
        """Reject all collected (untouched) items. Returns count."""
        async with self.session() as s:
            result = await s.execute(
                select(NewsItemDB).where(NewsItemDB.status == NewsStatus.COLLECTED)
            )
            items = result.scalars().all()
            for item in items:
                item.status = NewsStatus.REJECTED
                item.rejected_reason = "bulk-rejected by admin"
                item.moderated_at = datetime.utcnow()
            await s.commit()
            return len(items)

    # --- reads ------------------------------------------------------------

    async def get_item(self, news_id: str) -> ProcessedNewsItem | NewsItem | None:
        async with self.session() as s:
            try:
                item = await s.get(NewsItemDB, uuid.UUID(news_id))
            except ValueError:
                return None
            return _to_model(item) if item else None

    async def get_by_status(
        self, status: NewsStatus, limit: int = 20, offset: int = 0
    ) -> list[ProcessedNewsItem | NewsItem]:
        """Items in a given status. Moderation queue = get_by_status(PROCESSED)."""
        order = (
            NewsItemDB.published_to_channel_at.desc()
            if status == NewsStatus.PUBLISHED
            else NewsItemDB.created_at.desc()
        )
        async with self.session() as s:
            result = await s.execute(
                select(NewsItemDB)
                .where(NewsItemDB.status == status)
                .order_by(order)
                .offset(offset)
                .limit(limit)
            )
            return [_to_model(i) for i in result.scalars().all()]

    async def get_collected_news(self, limit: int = 20, offset: int = 0) -> list[NewsItem]:
        """Raw collected items awaiting admin review (the "Новыя" queue)"""
        async with self.session() as s:
            result = await s.execute(
                select(NewsItemDB)
                .where(NewsItemDB.status == NewsStatus.COLLECTED)
                .order_by(NewsItemDB.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return [_to_model(i) for i in result.scalars().all()]

    async def get_unprocessed_news(self, limit: int = 10) -> list[NewsItem]:
        """Collected items relevant enough to be worth AI processing"""
        async with self.session() as s:
            result = await s.execute(
                select(NewsItemDB)
                .where(
                    NewsItemDB.status == NewsStatus.COLLECTED,
                    NewsItemDB.relevance_score >= settings.min_relevance_score,
                )
                .order_by(NewsItemDB.created_at.asc())
                .limit(limit)
            )
            return [_to_model(i) for i in result.scalars().all()]

    async def next_queued_item(self) -> ProcessedNewsItem | None:
        """Oldest approved item waiting for the publisher"""
        async with self.session() as s:
            result = await s.execute(
                select(NewsItemDB)
                .where(NewsItemDB.status == NewsStatus.QUEUED)
                .order_by(NewsItemDB.moderated_at.asc())
                .limit(1)
            )
            item = result.scalar_one_or_none()
            return _to_model(item) if item else None

    async def url_exists(self, url: str) -> bool:
        async with self.session() as s:
            result = await s.execute(select(NewsItemDB.id).where(NewsItemDB.url == url).limit(1))
            return result.scalar_one_or_none() is not None

    async def count_by_status(self, status: NewsStatus) -> int:
        async with self.session() as s:
            result = await s.execute(
                select(func.count()).select_from(NewsItemDB).where(NewsItemDB.status == status)
            )
            return result.scalar_one()

    async def published_in_last_hour(self) -> int:
        """For the publisher's rate limit — counted from the DB, no in-memory state"""
        cutoff = datetime.utcnow() - timedelta(hours=1)
        async with self.session() as s:
            result = await s.execute(
                select(func.count())
                .select_from(NewsItemDB)
                .where(
                    NewsItemDB.status == NewsStatus.PUBLISHED,
                    NewsItemDB.published_to_channel_at >= cutoff,
                )
            )
            return result.scalar_one()

    async def get_stats(self) -> Stats:
        async with self.session() as s:
            by_status_rows = await s.execute(
                select(NewsItemDB.status, func.count()).group_by(NewsItemDB.status)
            )
            by_status = {NewsStatus(status).value: count for status, count in by_status_rows}

            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = datetime.utcnow() - timedelta(days=7)
            published_today = await s.execute(
                select(func.count())
                .select_from(NewsItemDB)
                .where(
                    NewsItemDB.status == NewsStatus.PUBLISHED,
                    NewsItemDB.published_to_channel_at >= today_start,
                )
            )
            published_week = await s.execute(
                select(func.count())
                .select_from(NewsItemDB)
                .where(
                    NewsItemDB.status == NewsStatus.PUBLISHED,
                    NewsItemDB.published_to_channel_at >= week_start,
                )
            )
            last_created = await s.execute(select(func.max(NewsItemDB.created_at)))

            return Stats(
                total_collected=sum(by_status.values()),
                by_status=by_status,
                published_today=published_today.scalar_one(),
                published_this_week=published_week.scalar_one(),
                last_collection_time=last_created.scalar_one_or_none(),
            )


# Global database manager instance
db_manager = DatabaseManager()
