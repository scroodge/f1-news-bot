"""Tests for the news item lifecycle in the database layer (SQLite in-memory)"""

from datetime import datetime

import pytest

from src.database import DatabaseManager
from src.models import NewsItem, NewsStatus, ProcessedNewsItem, SourceType


@pytest.fixture
async def db():
    manager = DatabaseManager("sqlite+aiosqlite://")
    await manager.create_tables()
    yield manager
    await manager.close()


def make_item(url="https://example.com/news/1") -> NewsItem:
    return NewsItem(
        title="Verstappen wins the Grand Prix",
        content="Max Verstappen won the race at Silverstone.",
        url=url,
        source="test",
        source_type=SourceType.RSS,
        published_at=datetime(2026, 7, 5, 12, 0),
        relevance_score=0.9,
    )


def make_processed(item_id: str) -> ProcessedNewsItem:
    return ProcessedNewsItem(
        id=item_id,
        title="Verstappen wins the Grand Prix",
        content="Max Verstappen won the race at Silverstone.",
        url="https://example.com/news/1",
        source="test",
        source_type=SourceType.RSS,
        published_at=datetime(2026, 7, 5, 12, 0),
        summary="Ферстаппен выиграл Гран-при",
        key_points=["победа"],
        importance_level=4,
        tags=["гонка"],
    )


async def test_full_lifecycle_to_published(db):
    item_id = await db.save_news_item(make_item())
    assert item_id is not None

    stored = await db.get_item(item_id)
    assert stored.status == NewsStatus.COLLECTED

    assert await db.mark_processed(item_id, make_processed(item_id))
    assert (await db.get_item(item_id)).status == NewsStatus.PROCESSED

    assert await db.approve(item_id)
    assert (await db.get_item(item_id)).status == NewsStatus.QUEUED

    queued = await db.next_queued_item()
    assert queued is not None and queued.id == item_id

    assert await db.mark_published(item_id, telegram_message_id=42)
    final = await db.get_item(item_id)
    assert final.status == NewsStatus.PUBLISHED
    assert final.telegram_message_id == 42
    assert final.published_to_channel_at is not None


async def test_reject_path(db):
    item_id = await db.save_news_item(make_item())
    await db.mark_processed(item_id, make_processed(item_id))

    assert await db.reject(item_id, reason="spam")
    stored = await db.get_item(item_id)
    assert stored.status == NewsStatus.REJECTED
    assert stored.rejected_reason == "spam"

    # Rejected items can't be approved
    assert not await db.approve(item_id)


async def test_cannot_approve_unprocessed(db):
    item_id = await db.save_news_item(make_item())
    assert not await db.approve(item_id)  # still COLLECTED
    assert (await db.get_item(item_id)).status == NewsStatus.COLLECTED


async def test_published_cannot_be_rejected(db):
    item_id = await db.save_news_item(make_item())
    await db.mark_processed(item_id, make_processed(item_id))
    await db.approve(item_id)
    await db.mark_published(item_id)

    assert not await db.reject(item_id)
    assert (await db.get_item(item_id)).status == NewsStatus.PUBLISHED


async def test_url_dedup(db):
    first = await db.save_news_item(make_item())
    duplicate = await db.save_news_item(make_item())
    assert first is not None
    assert duplicate is None  # unique URL constraint
    assert await db.url_exists("https://example.com/news/1")


async def test_queue_reads_and_counts(db):
    for i in range(3):
        item_id = await db.save_news_item(make_item(url=f"https://example.com/news/{i}"))
        await db.mark_processed(item_id, make_processed(item_id))

    assert await db.count_by_status(NewsStatus.PROCESSED) == 3
    page = await db.get_by_status(NewsStatus.PROCESSED, limit=2)
    assert len(page) == 2

    rejected = await db.reject_all_pending()
    assert rejected == 3
    assert await db.count_by_status(NewsStatus.PROCESSED) == 0
    assert await db.count_by_status(NewsStatus.REJECTED) == 3


async def test_rate_limit_counter(db):
    assert await db.published_in_last_hour() == 0
    item_id = await db.save_news_item(make_item())
    await db.mark_processed(item_id, make_processed(item_id))
    await db.approve(item_id)
    await db.mark_published(item_id)
    assert await db.published_in_last_hour() == 1
