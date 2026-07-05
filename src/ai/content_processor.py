"""
Content processor for AI-powered news analysis.

Pipeline step: collected -> processed (awaiting admin moderation in the bot),
or -> rejected when the rule-based moderator turns it down. State lives in
PostgreSQL; no Redis queues.
"""

import asyncio
import logging

from ..database import db_manager
from ..models import NewsItem, ProcessedNewsItem, ProcessingResult
from ..moderator.content_moderator import ContentModerator
from ..services.redis_service import redis_service
from .ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class ContentProcessor:
    """AI-powered content processor"""

    def __init__(self):
        self.ollama_client = OllamaClient()
        self.moderator = ContentModerator()

    async def initialize(self) -> bool:
        """Initialize the processor"""
        await self.ollama_client.initialize()

        if not await self.ollama_client.check_health():
            logger.error("LLM server is not available")
            return False

        logger.info("Content processor initialized successfully")
        return True

    def _detect_language(self, text: str) -> str:
        """Detect if text is in Russian or other language"""
        cyrillic_chars = sum(1 for char in text if "Ѐ" <= char <= "ӿ")
        total_chars = len([char for char in text if char.isalpha()])

        if total_chars == 0:
            return "unknown"

        cyrillic_ratio = cyrillic_chars / total_chars
        return "russian" if cyrillic_ratio > 0.3 else "other"

    async def process_news_batch(self, news_items: list[NewsItem]) -> list[ProcessingResult]:
        """Process a batch of news items"""
        results = []

        for news_item in news_items:
            try:
                result = await self.process_single_news(news_item)
                results.append(result)

                # Small delay to avoid overwhelming the LLM server
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error processing news item {news_item.id}: {e}")
                results.append(ProcessingResult(success=False, error_message=str(e)))

        return results

    async def process_single_news(self, news_item: NewsItem) -> ProcessingResult:
        """Process a single news item and store the outcome in the DB"""
        try:
            title_lang = self._detect_language(news_item.title)
            content_lang = self._detect_language(news_item.content)

            if title_lang == "russian" and content_lang == "russian":
                # NOTE: fast path is slated for removal in Phase 2 — the
                # Belarusian pipeline sends everything through the LLM.
                logger.info(f"Fast processing Russian news: {news_item.title[:50]}...")
                result = self._process_russian_news_fast(news_item)
            else:
                logger.info(f"Full processing with LLM: {news_item.title[:50]}...")
                result = await self.ollama_client.process_news_item(news_item)

            if not (result.success and result.news_item):
                logger.error(f"Failed to process news item: {result.error_message}")
                return result

            await db_manager.mark_processed(news_item.id, result.news_item)

            # Rule-based moderation: auto-reject spam/low quality before a
            # human ever sees it. Approved items stay PROCESSED for the admin.
            moderation = self.moderator.moderate_news_item(result.news_item)
            if not moderation["approved"]:
                reason = "; ".join(moderation["reasons"]) or "rejected by content rules"
                await db_manager.reject(news_item.id, reason)
                logger.info(f"Auto-rejected: {news_item.title[:50]}... ({reason})")
            else:
                await redis_service.signal_new_pending()
                logger.info(f"Awaiting moderation: {news_item.title[:50]}...")

            return result

        except Exception as e:
            logger.error(f"Error processing news item: {e}")
            return ProcessingResult(success=False, error_message=str(e))

    def _process_russian_news_fast(self, news_item: NewsItem) -> ProcessingResult:
        """Fast processing for Russian news without the LLM"""
        try:
            data = self.ollama_client.process_russian_news_fast(news_item)

            processed_news = ProcessedNewsItem(
                id=news_item.id,
                title=news_item.title,
                content=news_item.content,
                url=news_item.url,
                source=news_item.source,
                source_type=news_item.source_type,
                published_at=news_item.published_at,
                created_at=news_item.created_at,
                summary=data["summary"],
                key_points=data["key_points"],
                sentiment=data["sentiment"],
                importance_level=data["importance_level"],
                formatted_content=data["formatted_content"],
                tags=data["tags"],
                relevance_score=data["relevance_score"],
                translated_title=data.get("translated_title"),
                translated_summary=data.get("translated_summary"),
                translated_key_points=data.get("translated_key_points") or [],
                original_language="russian",
                image_url=news_item.image_url,
                video_url=news_item.video_url,
                media_type=news_item.media_type,
            )

            return ProcessingResult(success=True, news_item=processed_news)

        except Exception as e:
            logger.error(f"Error in fast processing: {e}")
            return ProcessingResult(success=False, error_message=str(e))

    async def process_pending_news(self, limit: int = 10) -> list[ProcessingResult]:
        """Process pending news items from database"""
        try:
            pending_news = await db_manager.get_unprocessed_news(limit)

            if not pending_news:
                logger.info("No pending news items to process")
                return []

            logger.info(f"Processing {len(pending_news)} pending news items")
            results = await self.process_news_batch(pending_news)

            successful = sum(1 for r in results if r.success)
            logger.info(
                f"Processing completed: {successful} successful, {len(results) - successful} failed"
            )
            return results

        except Exception as e:
            logger.error(f"Error processing pending news: {e}")
            return []

    async def close(self):
        """Close the processor"""
        await self.ollama_client.close()
        logger.info("Content processor closed")
