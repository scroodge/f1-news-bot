"""
Admin API for the Telegram Mini App.

All routes require a valid Telegram initData from the configured admin.
State transitions reuse the same DatabaseManager the bot uses — approving
here queues the item for the bot process's publisher loop.
"""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from ..config import settings
from ..database import db_manager
from ..editorial import canonical_url, editorial_priority, editorial_reasons
from ..editorial_learning import POLICY_VERSION, REASON_LABELS, shadow_recommendation
from ..models import NewsItem, NewsStatus, ProcessedNewsItem
from ..provenance import article_url, named_attributions, quality_info
from ..stories import representative
from ..telegram_bot.formatting import format_channel_post
from .auth import require_admin

# Lazy import to avoid circular dependency at module level
_content_processor = None


async def get_content_processor():
    global _content_processor
    if _content_processor is None:
        from ..ai.content_processor import ContentProcessor

        _content_processor = ContentProcessor()
    return _content_processor


logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

router = APIRouter(prefix="/admin", tags=["admin"])
api = APIRouter(prefix="/admin/api", tags=["admin-api"], dependencies=[Depends(require_admin)])


# --- static frontend --------------------------------------------------------


@router.get("", include_in_schema=False)
async def miniapp_index():
    return FileResponse(STATIC_DIR / "index.html")


# --- serialization ----------------------------------------------------------


def _serialize(item: ProcessedNewsItem | NewsItem, with_preview: bool = True) -> dict:
    is_processed = isinstance(item, ProcessedNewsItem)
    data: dict = {
        "id": item.id,
        "title": item.title,
        "title_be": item.translated_title if is_processed else None,
        "content": item.content,
        "summary": item.translated_summary if is_processed else "",
        "short_summary": item.summary if is_processed else "",
        "key_points": item.key_points if is_processed else [],
        "tags": item.tags if is_processed else [],
        "source": item.source,
        "source_type": item.source_type.value,
        "url": item.url,
        "image_url": item.image_url,
        "relevance_score": item.relevance_score,
        "editorial_priority": editorial_priority(item),
        "editorial_reasons": editorial_reasons(item),
        "text_quality": quality_info(item),
        "source_references": (item.collection_info or {}).get("references", []),
        "named_attributions": named_attributions(item.content, item.url),
        "story_id": item.story_id,
        "shadow": shadow_recommendation(item),
        "importance_level": item.importance_level if is_processed else 1,
        "sentiment": item.sentiment if is_processed else "neutral",
        "original_language": item.original_language if is_processed else None,
        "status": item.status.value,
        "published_at": item.published_at.isoformat(),
        "created_at": item.created_at.isoformat(),
        "published_to_channel_at": (
            item.published_to_channel_at.isoformat()
            if is_processed and item.published_to_channel_at
            else None
        ),
        "rejected_reason": item.rejected_reason if is_processed else None,
        "has_translation": is_processed,
        "llm_usage": item.llm_usage if is_processed else None,
        "original_content": item.content if is_processed else None,
    }
    if with_preview:
        if is_processed:
            data["preview"] = format_channel_post(item)
        else:
            snippet = (item.content[:300] + "...") if len(item.content) > 300 else item.content
            data["preview"] = f"📰 {item.title}\n\n{snippet}\n\n🔗 {item.url}"
    return data


def _editorial_actor(admin: dict) -> dict:
    return {
        "kind": "human" if admin.get("id") else "demo",
        "id": str(admin.get("id", "")),
        "interface": "miniapp",
    }


class FeedbackRequest(BaseModel):
    reason_code: str = "unspecified"
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("reason_code")
    @classmethod
    def validate_reason(cls, value):
        if value not in REASON_LABELS:
            raise ValueError("Невядомая прычына рашэння")
        return value


class EditRequest(FeedbackRequest):
    title_be: str | None = Field(default=None, max_length=300)
    summary: str | None = Field(default=None, max_length=8000)
    key_points: list[str] | None = None
    tags: list[str] | None = None
    importance_level: int | None = Field(default=None, ge=1, le=5)


# --- queue ------------------------------------------------------------------


@api.get("/queue")
async def get_queue(page: int = 0, page_size: int = 10):
    total = await db_manager.count_by_status(NewsStatus.PROCESSED)
    items = await db_manager.get_by_status(
        NewsStatus.PROCESSED, limit=page_size, offset=page * page_size
    )
    return {
        "items": [_serialize(i) for i in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@api.get("/items/{item_id}")
async def get_item(item_id: str):
    item = await db_manager.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return _serialize(item)


@api.post("/items/{item_id}/approve")
async def approve_item(
    item_id: str, feedback: FeedbackRequest | None = None, admin: dict = Depends(require_admin)
):
    feedback = feedback or FeedbackRequest()
    if not await db_manager.approve(
        item_id, actor=_editorial_actor(admin), reason_code=feedback.reason_code, note=feedback.note
    ):
        raise HTTPException(status_code=409, detail="Item is not awaiting moderation")
    logger.info(f"Mini App: approved {item_id}")
    return {"ok": True, "status": NewsStatus.QUEUED.value}


@api.post("/items/{item_id}/reject")
async def reject_item(
    item_id: str, feedback: FeedbackRequest | None = None, admin: dict = Depends(require_admin)
):
    feedback = feedback or FeedbackRequest()
    if not await db_manager.reject(
        item_id,
        reason="rejected by admin (mini app)",
        actor=_editorial_actor(admin),
        reason_code=feedback.reason_code,
        note=feedback.note,
    ):
        raise HTTPException(status_code=409, detail="Item cannot be rejected")
    logger.info(f"Mini App: rejected {item_id}")
    return {"ok": True, "status": NewsStatus.REJECTED.value}


@api.post("/items/{item_id}/edit")
async def edit_item(item_id: str, edit: EditRequest, admin: dict = Depends(require_admin)):
    fields: dict = {}
    if edit.title_be is not None:
        fields["translated_title"] = edit.title_be.strip()
    if edit.summary is not None:
        fields["summary"] = edit.summary.strip()
        fields["translated_summary"] = edit.summary.strip()
    if edit.key_points is not None:
        fields["key_points"] = edit.key_points
    if edit.tags is not None:
        fields["tags"] = [t.strip().lstrip("#") for t in edit.tags if t.strip()]
    if edit.importance_level is not None:
        fields["importance_level"] = edit.importance_level
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to edit")

    if not await db_manager.update_fields(
        item_id,
        editorial_actor=_editorial_actor(admin),
        feedback_reason=edit.reason_code,
        feedback_note=edit.note,
        **fields,
    ):
        raise HTTPException(status_code=404, detail="Item not found")

    item = await db_manager.get_item(item_id)
    logger.info(f"Mini App: edited {item_id} ({', '.join(fields)})")
    return _serialize(item)


# --- raw queue (collected items awaiting admin translate decision) -----------


@api.get("/queue/raw")
async def get_raw_queue(page: int = Query(0, ge=0), page_size: int = Query(10, ge=1, le=50)):
    groups, total = await db_manager.get_collected_stories(limit=page_size, offset=page * page_size)
    items = []
    for members in groups:
        primary = representative(members)
        data = _serialize(primary)
        data["related_items"] = [_serialize(i) for i in members if i.id != primary.id]
        data["story_size"] = len(members)
        items.append(data)
    return {
        "items": items,
        "total": total,
        "total_articles": await db_manager.count_by_status(NewsStatus.COLLECTED),
        "page": page,
        "page_size": page_size,
    }


@api.post("/queue/raw/reject-all")
async def reject_all_raw(admin: dict = Depends(require_admin)):
    count = await db_manager.reject_all_collected(actor=_editorial_actor(admin))
    logger.info(f"Mini App: bulk-rejected {count} collected items")
    return {"ok": True, "count": count}


# --- admin-triggered AI actions ----------------------------------------------


class CollectOriginalRequest(BaseModel):
    url: str = Field(max_length=2048)


@api.post("/items/{item_id}/collect-original")
async def collect_original(item_id: str, request: CollectOriginalRequest):
    item = await db_manager.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Навіна не знойдзена")
    url = canonical_url(request.url)
    attributed = {r.get("url") for r in (item.collection_info or {}).get("references", [])}
    if url not in attributed or not article_url(url):
        raise HTTPException(status_code=400, detail="Спасылка не пацверджана атрыбуцыяй артыкула")
    original = await db_manager.get_item_by_url(url)
    if original is None:
        from ..collectors.web_scraper import WebScraperCollector

        collector = WebScraperCollector(sources=[])
        try:
            original = await collector.fetch_reference(url)
        except Exception:
            logger.exception("Failed to fetch attributed original: %s", url)
            original = None
        finally:
            await collector.close()
        if original is None:
            raise HTTPException(
                status_code=422, detail="Не ўдалося атрымаць тэкст. Адкрыйце спасылку на выданне."
            )
        original.story_id = item.story_id
        # None means the unique URL constraint hit a row stored under a non-canonical
        # spelling (saved before canonical_url existed), which the lookup above misses.
        if await db_manager.save_news_item(original) is None:
            raise HTTPException(
                status_code=409, detail="Гэты артыкул ужо ёсць у базе пад іншай спасылкай."
            )
        original = await db_manager.get_item_by_url(url)
    await db_manager.merge_stories(item_id, original.id)
    return _serialize(await db_manager.get_item(original.id))


@api.post("/items/{item_id}/translate")
async def translate_item(
    item_id: str,
    allow_incomplete: bool = False,
    feedback: FeedbackRequest | None = None,
    admin: dict = Depends(require_admin),
):
    item = await db_manager.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.status not in (NewsStatus.COLLECTED, NewsStatus.PROCESSED):
        raise HTTPException(
            status_code=409, detail="Item cannot be translated in its current state"
        )
    quality = quality_info(item)
    if quality["needs_confirmation"] and not allow_incomplete:
        raise HTTPException(
            status_code=409, detail=quality["label"] + ". Пацвердзіце пераклад даступнага тэксту."
        )
    feedback = feedback or FeedbackRequest()
    if not await db_manager.record_editorial_action(
        item_id,
        "translation_requested",
        actor=_editorial_actor(admin),
        reason_code=feedback.reason_code,
        note=feedback.note,
    ):
        raise HTTPException(status_code=409, detail="Статус навіны ўжо змяніўся")
    processor = await get_content_processor()
    # Run translation in background, return immediately
    asyncio.create_task(_run_translate(item_id, processor))
    return {"ok": True, "status": "started"}


async def _run_translate(item_id: str, processor):
    """Background task for translation."""
    try:
        await processor.translate_news(item_id)
    except Exception as e:
        logger.error(f"Background translate failed for {item_id}: {e}")


@api.get("/items/{item_id}/progress")
async def translate_progress(item_id: str):
    processor = await get_content_processor()
    prog = processor.get_progress(item_id)
    if prog is None:
        return {"step": "idle", "detail": "", "finished": False}
    return {
        "step": prog.step,
        "detail": prog.detail,
        "chunk_current": prog.chunk_current,
        "chunk_total": prog.chunk_total,
        "finished": prog.finished,
        "success": prog.success,
        "error": prog.error,
    }


@api.post("/items/{item_id}/generate-keypoints")
async def generate_keypoints(item_id: str, admin: dict = Depends(require_admin)):
    item = await db_manager.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.status != NewsStatus.PROCESSED:
        raise HTTPException(status_code=409, detail="Item must be translated first")
    await db_manager.record_editorial_action(
        item_id, "keypoints_requested", actor=_editorial_actor(admin)
    )
    processor = await get_content_processor()
    ok = await processor.generate_keypoints(item_id)
    if not ok:
        raise HTTPException(
            status_code=500, detail="Key-points generation failed (check Claude API)"
        )
    updated = await db_manager.get_item(item_id)
    logger.info(f"Mini App: generated key points for {item_id}")
    return _serialize(updated)


# --- history & stats --------------------------------------------------------


@api.get("/published")
async def get_published(limit: int = 20):
    items = await db_manager.get_by_status(NewsStatus.PUBLISHED, limit=limit)
    return {"items": [_serialize(i, with_preview=True) for i in items]}


@api.get("/rejected")
async def get_rejected(limit: int = 20):
    items = await db_manager.get_by_status(NewsStatus.REJECTED, limit=limit)
    return {"items": [_serialize(i, with_preview=False) for i in items]}


@api.get("/stats")
async def get_stats():
    stats = await db_manager.get_stats()
    return {
        "stats": stats.model_dump(),
        "pending": await db_manager.count_by_status(NewsStatus.PROCESSED),
        "queued": await db_manager.count_by_status(NewsStatus.QUEUED),
        "published_last_hour": await db_manager.published_in_last_hour(),
        "max_posts_per_hour": settings.max_posts_per_hour,
    }


@api.get("/items/{item_id}/history")
async def editorial_history(item_id: str, limit: int = Query(20, ge=1, le=50)):
    from uuid import UUID

    try:
        UUID(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Навіна не знойдзена") from exc
    return {"events": await db_manager.get_editorial_history(item_id, limit=limit)}


@api.get("/editorial/summary")
async def editorial_summary():
    return {
        **await db_manager.get_editorial_summary(),
        "mode": "shadow",
        "engine": "rules",
        "policy_version": POLICY_VERSION,
        "automatic_actions": False,
        "reason_options": [{"code": code, "label": label} for code, label in REASON_LABELS.items()],
    }
