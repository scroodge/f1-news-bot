"""
Content processor: admin-triggered translate + key-points generation.

No auto-processing loop. Items stay COLLECTED until the admin explicitly
clicks "Translate" in the Mini App — then the chosen LLM backend (Ollama
or Claude) produces the Belarusian translation. A separate action triggers
Claude to generate the 🔑 Галоўнае: key points from translated text.
"""

import logging

from ..config import settings
from ..database import db_manager
from ..models import NewsItem, ProcessedNewsItem
from ..services.redis_service import redis_service
from .backends import ClaudeBackend, EmbeddingClient, OllamaBackend
from .dedup import find_duplicate
from .schemas import NewsAnalysis

logger = logging.getLogger(__name__)


class ContentProcessor:
    """Admin-triggered content processing (translate + key points)"""

    def __init__(self):
        self.embeddings = EmbeddingClient()
        self._ollama: OllamaBackend | None = None
        self._claude: ClaudeBackend | None = None

    async def initialize(self) -> bool:
        # Just check embeddings backend is reachable
        logger.info("Content processor initialized")
        return True

    def _get_backend(self, provider: str = "ollama") -> OllamaBackend | ClaudeBackend:
        if provider == "claude":
            if self._claude is None:
                self._claude = ClaudeBackend()
            return self._claude
        if self._ollama is None:
            self._ollama = OllamaBackend()
        return self._ollama

    def _detect_language(self, text: str) -> str:
        """Coarse source-language detection (stored as original_language)"""
        cyrillic = sum(1 for ch in text if "Ѐ" <= ch <= "ӿ")
        letters = sum(1 for ch in text if ch.isalpha())
        if letters == 0:
            return "unknown"
        if cyrillic / letters > 0.3:
            return "be" if any(ch in "ўЎіІ" for ch in text) else "ru"
        return "en"

    async def _check_duplicate(self, news_item: NewsItem) -> bool:
        """Embed the item and reject it when it's a re-telling of a recent story.
        Returns True when the item was rejected as a duplicate."""
        if not settings.dedup_enabled:
            return False
        embedding = await self.embeddings.embed(f"{news_item.title}\n{news_item.content[:1500]}")
        if embedding is None:
            return False
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

    async def translate_news(self, item_id: str, provider: str = "ollama") -> bool:
        """Translate a collected item using the chosen LLM backend.
        Returns True on success, False on failure/rejection."""
        item = await db_manager.get_item(item_id)
        if item is None or not isinstance(item, NewsItem):
            logger.warning(f"translate_news: item {item_id} not found or not COLLECTED")
            return False
        try:
            if await self._check_duplicate(item):
                return False
            backend = self._get_backend(provider)
            analysis = await backend.analyze_with_retries(item.title, item.content)
            if analysis is None:
                logger.error(f"LLM analysis failed for {item.title[:60]}...")
                return False
            processed = self._build_processed_item(item, analysis)
            await db_manager.mark_processed(item.id, processed)
            await redis_service.signal_new_pending()
            logger.info(f"Translated ({provider}): {analysis.title_be[:60]}...")
            return True
        except Exception as e:
            logger.error(f"translate_news failed: {e}", exc_info=True)
            return False

    async def generate_keypoints(self, item_id: str) -> bool:
        """Generate 🔑 Галоўнае: key points via Claude for a translated item.
        Returns True on success."""
        item = await db_manager.get_item(item_id)
        if item is None or not isinstance(item, ProcessedNewsItem):
            logger.warning(f"generate_keypoints: item {item_id} not found or not translated")
            return False
        try:
            title_be = item.translated_title or item.title
            summary_be = item.translated_summary or item.summary
            backend = self._get_backend("claude")
            key_points = await backend.generate_key_points(title_be, summary_be)
            await db_manager.update_fields(item_id, key_points=key_points)
            logger.info(f"Key points generated for {title_be[:60]}...")
            return True
        except Exception as e:
            logger.error(f"generate_keypoints failed: {e}", exc_info=True)
            return False

    async def close(self):
        if self._ollama:
            await self._ollama.close()
        if self._claude:
            await self._claude.close()
        await self.embeddings.close()
        logger.info("Content processor closed")
