"""
Content processor: admin-triggered translate + key-points generation.

Pipeline: TranslateGemma 12B (RU→BE) → Sonnet (polish) → Haiku (analyze).
No auto-processing loop. Admin triggers actions via the Mini App.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field

from ..config import settings
from ..database import db_manager
from ..models import NewsItem, NewsStatus, ProcessedNewsItem
from ..services.redis_service import redis_service
from .backends import ClaudeBackend, EmbeddingClient, OllamaBackend
from .dedup import find_duplicate
from .schemas import NewsAnalysis

logger = logging.getLogger(__name__)


@dataclass
class TranslationProgress:
    step: str = "starting"
    detail: str = ""
    chunk_current: int = 0
    chunk_total: int = 0
    started_at: float = field(default_factory=time.time)
    finished: bool = False
    success: bool = False
    error: str = ""


class ContentProcessor:
    """Admin-triggered content processing (translate + key points)"""

    def __init__(self):
        self.embeddings = EmbeddingClient()
        self._ollama: OllamaBackend | None = None
        self._claude: ClaudeBackend | None = None
        self._warmed_up = False
        self._progress: dict[str, TranslationProgress] = {}

    def get_progress(self, item_id: str) -> TranslationProgress | None:
        return self._progress.get(item_id)

    async def initialize(self) -> bool:
        logger.info("Content processor initialized")
        # Background warmup — first translate call will wait if it hasn't finished
        asyncio.create_task(self._warmup())
        return True

    async def _warmup(self):
        """Background warmup; translate_news will wait if not done yet."""
        ollama = self._get_ollama()
        await ollama.warmup()
        self._warmed_up = True

    def _get_ollama(self) -> OllamaBackend:
        if self._ollama is None:
            self._ollama = OllamaBackend()
        return self._ollama

    def _get_claude(self) -> ClaudeBackend:
        if self._claude is None:
            self._claude = ClaudeBackend()
        return self._claude

    def _detect_language(self, text: str) -> str:
        cyrillic = sum(1 for ch in text if "Ѐ" <= ch <= "ӿ")
        letters = sum(1 for ch in text if ch.isalpha())
        if letters == 0:
            return "unknown"
        if cyrillic / letters > 0.3:
            return "be" if any(ch in "ўЎіІ" for ch in text) else "ru"
        return "en"

    async def _check_duplicate(self, news_item: NewsItem) -> bool:
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
        self,
        news_item: NewsItem,
        analysis: NewsAnalysis,
        sonnet_summary: str = "",
        short_summary: str = "",
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
            summary=short_summary or sonnet_summary or analysis.summary_be,
            key_points=analysis.key_points_be,
            sentiment=analysis.sentiment,
            importance_level=analysis.importance_level,
            tags=analysis.tags_be,
            translated_title=analysis.title_be,
            translated_summary=sonnet_summary or analysis.summary_be,
            translated_key_points=analysis.key_points_be,
            original_language=self._detect_language(f"{news_item.title} {news_item.content}"),
        )

    async def translate_news(self, item_id: str, provider: str = "ollama") -> bool:
        """Translate an article using TG12B → Sonnet → analyze pipeline."""
        if not self._warmed_up:
            self._progress[item_id] = TranslationProgress(step="warmup", detail="Loading TG12B model...")
            await self._warmup()
        item = await db_manager.get_item(item_id)
        if item is None:
            logger.warning(f"translate_news: item {item_id} not found")
            return False
        if item.status.value not in ("collected", "processed"):
            logger.warning(f"translate_news: item {item_id} has status {item.status}")
            return False
        try:
            if item.status == NewsStatus.COLLECTED and await self._check_duplicate(item):
                return False

            progress = self._progress.setdefault(item_id, TranslationProgress())

            # Step 1: TranslateGemma 12B RU→BE
            progress.step = "translating"
            progress.detail = "Translating with TG12B..."
            ollama = self._get_ollama()
            raw_be = await ollama.translate(item.title, item.content)

            # Step 2: TG12B generates short summary for channel preview (free)
            progress.step = "summary"
            progress.detail = "Generating short summary..."
            short_summary = await ollama.generate_summary(raw_be)

            # Step 3: Sonnet polish (full text only)
            progress.step = "polishing"
            progress.detail = "Polishing with Sonnet..."
            claude = self._get_claude()
            title_be, summary_be = await claude.polish(raw_be)
            polish_usage = claude.last_usage

            # Step 4: Haiku analyzes (key points, tags, sentiment) — does NOT touch summary
            progress.step = "analyzing"
            progress.detail = "Analyzing with Haiku..."
            analysis = await claude.analyze(title_be, summary_be)
            total_usage = {
                "tg12b": ollama.last_usage,
                "sonnet_polish": polish_usage,
                "claude_analyze": claude.last_usage,
            }

            processed = self._build_processed_item(
                item, analysis, sonnet_summary=summary_be, short_summary=short_summary
            )
            await db_manager.mark_processed(item.id, processed, llm_usage=total_usage)
            await redis_service.signal_new_pending()
            logger.info(f"Translated (TG12B→Sonnet): {analysis.title_be[:60]}...")

            progress.step = "done"
            progress.detail = "Translation complete"
            progress.finished = True
            progress.success = True
            return True
        except Exception as e:
            logger.error(f"translate_news failed: {e}", exc_info=True)
            progress = self._progress.get(item_id)
            if progress:
                progress.step = "error"
                progress.detail = str(e)[:200]
                progress.finished = True
                progress.error = str(e)[:200]
            return False

    async def generate_keypoints(self, item_id: str) -> bool:
        """Generate 🔑 Галоўнае: key points via Claude for a translated item."""
        item = await db_manager.get_item(item_id)
        if item is None or not isinstance(item, ProcessedNewsItem):
            logger.warning(f"generate_keypoints: item {item_id} not found or not translated")
            return False
        try:
            title_be = item.translated_title or item.title
            summary_be = item.translated_summary or item.summary
            backend = self._get_claude()
            key_points = await backend.generate_key_points(title_be, summary_be)
            await db_manager.update_fields(
                item_id, key_points=key_points, llm_usage=backend.last_usage
            )
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
