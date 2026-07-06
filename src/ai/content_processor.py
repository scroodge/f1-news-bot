"""
Content processor: the collected -> processed/rejected pipeline step.

Every item goes through the LLM (the channel publishes in Belarusian, so
Russian and English sources alike get translated — the old "Russian skips
AI" fast path is gone). Steps per item:

1. Embed title+content (bge-m3) and reject semantic duplicates of recent items.
2. One structured LLM call -> NewsAnalysis (Belarusian title/summary/points/tags).
3. Rule-based moderation; auto-reject spam/low quality.
4. Survivors become PROCESSED and wait for the admin.
"""

import asyncio
import logging

from ..config import settings
from ..database import db_manager
from ..models import NewsItem, ProcessedNewsItem, ProcessingResult
from ..moderator.content_moderator import ContentModerator
from ..services.redis_service import redis_service
from .backends import EmbeddingClient, LLMBackend, get_llm_backend
from .dedup import find_duplicate
from .schemas import NewsAnalysis

logger = logging.getLogger(__name__)


class ContentProcessor:
    """AI-powered content processor"""

    def __init__(self, backend: LLMBackend | None = None):
        self.backend = backend or get_llm_backend()
        self.embeddings = EmbeddingClient()
        self.moderator = ContentModerator()

    async def initialize(self) -> bool:
        if not await self.backend.check_health():
            logger.error(f"LLM backend '{self.backend.name}' is not available")
            return False
        logger.info(f"Content processor initialized (backend: {self.backend.name})")
        return True

    def _detect_language(self, text: str) -> str:
        """Coarse source-language detection (stored as original_language)"""
        cyrillic = sum(1 for ch in text if "Ѐ" <= ch <= "ӿ")
        letters = sum(1 for ch in text if ch.isalpha())
        if letters == 0:
            return "unknown"
        if cyrillic / letters > 0.3:
            # Belarusian-specific letters distinguish be from ru
            return "be" if any(ch in "ўЎіІ" for ch in text) else "ru"
        return "en"

    async def _check_duplicate(self, news_item: NewsItem) -> bool:
        """Embed the item and reject it when it's a re-telling of a recent story.
        Returns True when the item was rejected as a duplicate."""
        if not settings.dedup_enabled:
            return False
        embedding = await self.embeddings.embed(f"{news_item.title}\n{news_item.content[:1500]}")
        if embedding is None:
            return False  # embeddings down — degrade to URL-only dedup
        await db_manager.set_embedding(news_item.id, embedding)

        existing = await db_manager.get_recent_embeddings(
            days=settings.dedup_lookback_days, exclude_id=news_item.id
        )
        match = find_duplicate(embedding, existing, settings.dedup_similarity_threshold)
        if match is None:
            return False
        dup_id, score = match
        await db_manager.reject(news_item.id, reason=f"duplicate of {dup_id} (cosine {score:.2f})")
        logger.info(f"Rejected duplicate ({score:.2f}): {news_item.title[:60]}...")
        return True

    def _build_processed_item(
        self, news_item: NewsItem, analysis: NewsAnalysis
    ) -> ProcessedNewsItem:
        return ProcessedNewsItem(
            id=news_item.id,
            title=news_item.title,
            content=news_item.content,
            url=news_item.url,
            source=news_item.source,
            source_type=news_item.source_type,
            published_at=news_item.published_at,
            created_at=news_item.created_at,
            relevance_score=news_item.relevance_score,
            keywords=news_item.keywords,
            image_url=news_item.image_url,
            video_url=news_item.video_url,
            media_type=news_item.media_type,
            # Belarusian analysis
            summary=analysis.summary_be,
            key_points=analysis.key_points_be,
            sentiment=analysis.sentiment,
            importance_level=analysis.importance_level,
            tags=analysis.tags_be,
            translated_title=analysis.title_be,
            translated_summary=analysis.summary_be,
            translated_key_points=analysis.key_points_be,
            original_language=self._detect_language(f"{news_item.title} {news_item.content}"),
        )

    async def process_single_news(self, news_item: NewsItem) -> ProcessingResult:
        """Process one item and store the outcome in the DB"""
        try:
            if await self._check_duplicate(news_item):
                return ProcessingResult(success=False, error_message="duplicate")

            analysis = await self.backend.analyze_with_retries(news_item.title, news_item.content)
            if analysis is None:
                logger.error(f"LLM analysis failed: {news_item.title[:60]}...")
                return ProcessingResult(success=False, error_message="LLM analysis failed")

            processed = self._build_processed_item(news_item, analysis)
            await db_manager.mark_processed(news_item.id, processed)

            # Rule-based moderation: auto-reject spam/low quality before a
            # human ever sees it. Approved items stay PROCESSED for the admin.
            moderation = self.moderator.moderate_news_item(processed)
            if not moderation["approved"]:
                reason = "; ".join(moderation["reasons"]) or "rejected by content rules"
                await db_manager.reject(news_item.id, reason)
                logger.info(f"Auto-rejected: {news_item.title[:60]}... ({reason})")
            else:
                await redis_service.signal_new_pending()
                logger.info(f"Awaiting moderation: {analysis.title_be[:60]}...")

            return ProcessingResult(success=True, news_item=processed)

        except Exception as e:
            logger.error(f"Error processing news item: {e}", exc_info=True)
            return ProcessingResult(success=False, error_message=str(e))

    async def process_news_batch(self, news_items: list[NewsItem]) -> list[ProcessingResult]:
        results = []
        for news_item in news_items:
            results.append(await self.process_single_news(news_item))
            await asyncio.sleep(1)  # be gentle with the LLM server
        return results

    async def process_pending_news(self, limit: int = 10) -> list[ProcessingResult]:
        """Process pending news items from the database"""
        try:
            pending = await db_manager.get_unprocessed_news(limit)
            if not pending:
                logger.info("No pending news items to process")
                return []

            logger.info(f"Processing {len(pending)} pending news items")
            results = await self.process_news_batch(pending)
            ok = sum(1 for r in results if r.success)
            logger.info(f"Processing completed: {ok} successful, {len(results) - ok} failed")
            return results
        except Exception as e:
            logger.error(f"Error processing pending news: {e}")
            return []

    async def close(self):
        await self.backend.close()
        await self.embeddings.close()
        logger.info("Content processor closed")
