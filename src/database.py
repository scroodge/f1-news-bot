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
    Boolean,
    DateTime,
    Enum,
    Float,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    cast,
    func,
    select,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import settings
from .editorial import editorial_priority_sql
from .editorial_learning import (
    DRAFT_FIELDS,
    SOURCE_FIELDS,
    changes_between,
    shadow_recommendation,
    snapshot,
    stable_hash,
    training_eligible,
    version_context,
)
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

    story_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    collection_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    __table_args__ = (Index("ix_news_items_created_at", "created_at"),)

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


class EditorialEventDB(Base):
    """Append-only application journal; no cascading FK to mutable news rows."""

    __tablename__ = "editorial_events"
    __table_args__ = (
        Index("ix_editorial_events_news_created", "news_id", "created_at"),
        Index("ix_editorial_events_created", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    news_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    story_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    actor: Mapped[dict] = mapped_column(JSON, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    changes: Mapped[dict] = mapped_column(JSON, nullable=False)
    recommendation: Mapped[dict] = mapped_column(JSON, nullable=False)
    versions: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    draft_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    training_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def _append_editorial_event(
    session,
    item,
    kind,
    before=None,
    actor=None,
    reason="unspecified",
    note=None,
    recommendation=None,
):
    after = snapshot(item)
    changes = changes_between(before, after)
    actor = actor or {"kind": "system", "interface": "internal"}
    is_demo = (item.collection_info or {}).get("text_origin") == "demo"
    if is_demo:
        actor = {**actor, "kind": "demo"}
    session.add(
        EditorialEventDB(
            news_id=item.id,
            story_id=item.story_id or item.id.hex,
            kind=kind,
            actor=dict(actor),
            reason_code=reason,
            note=note,
            before=before,
            after=after,
            changes=changes,
            recommendation=recommendation or shadow_recommendation(item),
            versions={**version_context(), "execution_mode": "demo" if is_demo else "normal"},
            source_hash=stable_hash({k: after.get(k) for k in SOURCE_FIELDS}),
            draft_hash=stable_hash({k: after.get(k) for k in DRAFT_FIELDS}),
            training_eligible=training_eligible(kind, actor, reason, changes),
        )
    )


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
        "story_id": item.story_id or item.id.hex,
        "collection_info": item.collection_info or {},
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
                story_id=news_item.story_id or uuid.uuid4().hex,
                collection_info=news_item.collection_info,
            )
            s.add(db_item)
            try:
                await s.flush()
                _append_editorial_event(s, db_item, "collected")
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
            item = await s.get(NewsItemDB, uuid.UUID(news_id), with_for_update=True)
            if not item or item.status not in {NewsStatus.COLLECTED, NewsStatus.PROCESSED}:
                return False
            before, recommendation = snapshot(item), shadow_recommendation(item)
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
            _append_editorial_event(
                s, item, "draft_generated", before, recommendation=recommendation
            )
            await s.commit()
            return True

    async def approve(
        self, news_id: str, *, actor=None, reason_code="unspecified", note=None
    ) -> bool:
        """Admin approved: processed -> queued, with an atomic feedback snapshot."""
        return await self._transition(
            news_id,
            from_statuses={NewsStatus.PROCESSED},
            to_status=NewsStatus.QUEUED,
            actor=actor,
            reason_code=reason_code,
            note=note,
        )

    async def reject(
        self,
        news_id: str,
        reason: str | None = None,
        *,
        actor=None,
        reason_code="unspecified",
        note=None,
    ) -> bool:
        async with self.session() as s:
            item = await s.get(NewsItemDB, uuid.UUID(news_id), with_for_update=True)
            if not item or item.status not in {
                NewsStatus.COLLECTED,
                NewsStatus.PROCESSED,
                NewsStatus.QUEUED,
            }:
                return False
            before, recommendation = snapshot(item), shadow_recommendation(item)
            item.status = NewsStatus.REJECTED
            item.rejected_reason = reason
            item.moderated_at = datetime.utcnow()
            _append_editorial_event(
                s, item, "rejected", before, actor, reason_code, note, recommendation
            )
            await s.commit()
            return True

    async def mark_published(self, news_id: str, telegram_message_id: int | None = None) -> bool:
        """Publisher done: queued -> published"""
        async with self.session() as s:
            item = await s.get(NewsItemDB, uuid.UUID(news_id), with_for_update=True)
            if not item:
                return False
            item.status = NewsStatus.PUBLISHED
            item.telegram_message_id = telegram_message_id
            item.published_to_channel_at = datetime.utcnow()
            await s.commit()
            return True

    async def _transition(
        self,
        news_id: str,
        from_statuses: set,
        to_status: NewsStatus,
        *,
        actor=None,
        reason_code="unspecified",
        note=None,
    ) -> bool:
        async with self.session() as s:
            item = await s.get(NewsItemDB, uuid.UUID(news_id), with_for_update=True)
            if not item or NewsStatus(item.status) not in from_statuses:
                return False
            before, recommendation = snapshot(item), shadow_recommendation(item)
            item.status = to_status
            item.moderated_at = datetime.utcnow()
            _append_editorial_event(
                s, item, "approved", before, actor, reason_code, note, recommendation
            )
            await s.commit()
            return True

    async def update_fields(
        self,
        news_id: str,
        *,
        editorial_actor=None,
        feedback_reason="unspecified",
        feedback_note=None,
        event_type=None,
        **fields,
    ) -> bool:
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
            item = await s.get(NewsItemDB, uuid.UUID(news_id), with_for_update=True)
            if not item:
                return False
            before, recommendation = snapshot(item), shadow_recommendation(item)
            for key, value in fields.items():
                setattr(item, key, value)
            if before != snapshot(item):
                kind = event_type or ("edited" if editorial_actor else "system_updated")
                _append_editorial_event(
                    s,
                    item,
                    kind,
                    before,
                    editorial_actor,
                    feedback_reason,
                    feedback_note,
                    recommendation,
                )
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

    async def reject_all_pending(self, *, actor=None) -> int:
        """Reject everything awaiting moderation (PROCESSED). Returns count."""
        async with self.session() as s:
            result = await s.execute(
                select(NewsItemDB)
                .where(NewsItemDB.status == NewsStatus.PROCESSED)
                .with_for_update()
            )
            items = result.scalars().all()
            for item in items:
                before, recommendation = snapshot(item), shadow_recommendation(item)
                item.status = NewsStatus.REJECTED
                item.rejected_reason = "bulk-rejected by admin"
                item.moderated_at = datetime.utcnow()
                _append_editorial_event(
                    s, item, "bulk_rejected", before, actor, recommendation=recommendation
                )
            await s.commit()
            return len(items)

    async def reject_all_collected(self, *, actor=None) -> int:
        """Reject all collected (untouched) items. Returns count."""
        async with self.session() as s:
            result = await s.execute(
                select(NewsItemDB)
                .where(NewsItemDB.status == NewsStatus.COLLECTED)
                .with_for_update()
            )
            items = result.scalars().all()
            for item in items:
                before, recommendation = snapshot(item), shadow_recommendation(item)
                item.status = NewsStatus.REJECTED
                item.rejected_reason = "bulk-rejected by admin"
                item.moderated_at = datetime.utcnow()
                _append_editorial_event(
                    s, item, "bulk_rejected", before, actor, recommendation=recommendation
                )
            await s.commit()
            return len(items)

    async def record_editorial_action(
        self, news_id: str, kind: str, *, actor=None, reason_code="unspecified", note=None
    ) -> bool:
        """Record an intent such as translation selection; not a successful AI result."""
        if kind not in {"translation_requested", "keypoints_requested"}:
            raise ValueError("Unsupported editorial intent")
        async with self.session() as s:
            item = await s.get(NewsItemDB, uuid.UUID(news_id), with_for_update=True)
            if not item or item.status not in {NewsStatus.COLLECTED, NewsStatus.PROCESSED}:
                return False
            _append_editorial_event(s, item, kind, snapshot(item), actor, reason_code, note)
            await s.commit()
            return True

    async def get_editorial_history(self, news_id: str, limit: int = 20) -> list[dict]:
        async with self.session() as s:
            rows = (
                await s.execute(
                    select(EditorialEventDB)
                    .where(EditorialEventDB.news_id == uuid.UUID(news_id))
                    .order_by(EditorialEventDB.created_at.desc(), EditorialEventDB.id)
                    .limit(limit)
                )
            ).scalars()
            return [
                {
                    "id": str(row.id),
                    "news_id": str(row.news_id),
                    "story_id": row.story_id,
                    "kind": row.kind,
                    "actor": row.actor,
                    "reason_code": row.reason_code,
                    "note": row.note,
                    "before": row.before,
                    "after": row.after,
                    "changes": row.changes,
                    "recommendation": row.recommendation,
                    "versions": row.versions,
                    "source_hash": row.source_hash,
                    "draft_hash": row.draft_hash,
                    "training_eligible": row.training_eligible,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]

    async def get_editorial_summary(self) -> dict:
        async with self.session() as s:
            total = await s.scalar(select(func.count()).select_from(EditorialEventDB))
            eligible = EditorialEventDB.training_eligible.is_(True)
            events = await s.scalar(
                select(func.count()).select_from(EditorialEventDB).where(eligible)
            )
            stories = await s.scalar(
                select(func.count(func.distinct(EditorialEventDB.story_id))).where(eligible)
            )
            reasons = (
                await s.execute(
                    select(EditorialEventDB.reason_code, func.count())
                    .where(eligible)
                    .group_by(EditorialEventDB.reason_code)
                )
            ).all()
            selection = EditorialEventDB.recommendation["selection"].as_string()
            decisions = (
                await s.execute(
                    select(
                        EditorialEventDB.kind, EditorialEventDB.reason_code, selection, func.count()
                    )
                    .where(
                        eligible,
                        EditorialEventDB.before["status"].as_string() == NewsStatus.COLLECTED.value,
                        EditorialEventDB.kind.in_(["translation_requested", "rejected"]),
                    )
                    .group_by(EditorialEventDB.kind, EditorialEventDB.reason_code, selection)
                )
            ).all()
            comparable = matches = deferred = 0
            skip_reasons = {"duplicate", "low_novelty", "not_interesting", "outdated"}
            for kind, reason, suggested, count in decisions:
                if suggested == "human_review":
                    deferred += count
                elif kind == "translation_requested" or reason in skip_reasons:
                    comparable += count
                    target = "translate" if kind == "translation_requested" else "skip"
                    matches += count if suggested == target else 0
            return {
                "selection_baseline": {
                    "comparable": comparable,
                    "matches": matches,
                    "deferred": deferred,
                },
                "events_total": total or 0,
                "eligible_events": events or 0,
                "eligible_stories": stories or 0,
                "by_reason": dict(reasons),
            }

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
                .order_by(
                    func.date(NewsItemDB.created_at).desc(),
                    editorial_priority_sql(NewsItemDB).desc(),
                    NewsItemDB.created_at.desc(),
                    NewsItemDB.id,
                )
                .offset(offset)
                .limit(limit)
            )
            return [_to_model(i) for i in result.scalars().all()]

    async def get_story_candidates(self) -> list[NewsItem]:
        """One bounded read per collection cycle, shared by all new items."""
        async with self.session() as s:
            rows = await s.execute(
                select(NewsItemDB)
                .where(NewsItemDB.created_at >= datetime.utcnow() - timedelta(days=3))
                .order_by(NewsItemDB.created_at.desc())
                .limit(2000)
            )
            return [_to_model(row) for row in rows.scalars()]

    async def get_collected_stories(self, limit: int = 10, offset: int = 0):
        """Page story IDs first, then load all their collected members in one query."""
        key = func.coalesce(NewsItemDB.story_id, func.replace(cast(NewsItemDB.id, String), "-", ""))
        async with self.session() as s:
            total = await s.scalar(
                select(func.count(func.distinct(key))).where(
                    NewsItemDB.status == NewsStatus.COLLECTED
                )
            )
            keys = (
                (
                    await s.execute(
                        select(key)
                        .where(NewsItemDB.status == NewsStatus.COLLECTED)
                        .group_by(key)
                        .order_by(
                            func.max(func.date(NewsItemDB.created_at)).desc(),
                            func.max(editorial_priority_sql(NewsItemDB)).desc(),
                            func.max(NewsItemDB.created_at).desc(),
                            key,
                        )
                        .offset(offset)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
            if not keys:
                return [], total or 0
            rows = (
                (
                    await s.execute(
                        select(NewsItemDB)
                        .where(NewsItemDB.status == NewsStatus.COLLECTED, key.in_(keys))
                        .order_by(NewsItemDB.created_at, NewsItemDB.id)
                    )
                )
                .scalars()
                .all()
            )
            groups = {k: [] for k in keys}
            for row in rows:
                model = _to_model(row)
                groups[model.story_id].append(model)
            return list(groups.values()), total or 0

    async def get_item_by_url(self, url: str) -> NewsItem | None:
        async with self.session() as s:
            row = (
                await s.execute(select(NewsItemDB).where(NewsItemDB.url == url))
            ).scalar_one_or_none()
            return _to_model(row) if row else None

    async def merge_stories(self, first_id: str, second_id: str):
        """Attach a manually fetched cited original without altering any lifecycle state."""
        async with self.session() as s:
            first = await s.get(NewsItemDB, uuid.UUID(first_id))
            second = await s.get(NewsItemDB, uuid.UUID(second_id))
            if not first or not second:
                return
            key = first.story_id or first.id.hex
            other = second.story_id
            if other and other != key:
                await s.execute(
                    update(NewsItemDB).where(NewsItemDB.story_id == other).values(story_id=key)
                )
            first.story_id = key
            second.story_id = key
            await s.commit()

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
