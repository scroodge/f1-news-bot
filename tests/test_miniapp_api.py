"""Tests for the Mini App admin API (SQLite-backed, auth mocked to admin)"""

from datetime import datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import src.webapp.router as router_module
from src.database import DatabaseManager
from src.models import NewsItem, NewsStatus, ProcessedNewsItem, SourceType
from src.webapp.auth import require_admin
from src.webapp.router import api as admin_api


@pytest.fixture
async def client(monkeypatch):
    db = DatabaseManager("sqlite+aiosqlite://")
    await db.create_tables()
    monkeypatch.setattr(router_module, "db_manager", db)

    app = FastAPI()
    app.include_router(admin_api)
    app.dependency_overrides[require_admin] = lambda: {"id": 1}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, db
    await db.close()


async def seed_processed(db: DatabaseManager, url="https://example.com/n/1") -> str:
    item_id = await db.save_news_item(
        NewsItem(
            title="Verstappen wins",
            content="Race report text.",
            url=url,
            source="test",
            source_type=SourceType.RSS,
            published_at=datetime(2026, 7, 5, 12, 0),
            relevance_score=0.9,
        )
    )
    await db.mark_processed(
        item_id,
        ProcessedNewsItem(
            id=item_id,
            title="Verstappen wins",
            content="Race report text.",
            url=url,
            source="test",
            source_type=SourceType.RSS,
            published_at=datetime(2026, 7, 5, 12, 0),
            summary="Ферстапен перамог.",
            key_points=["перамога"],
            importance_level=4,
            tags=["гонка"],
            translated_title="Ферстапен выйграў гонку",
        ),
    )
    return item_id


async def test_queue_returns_pending_items_with_preview(client):
    http, db = client
    await seed_processed(db)
    response = await http.get("/admin/api/queue")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["title_be"] == "Ферстапен выйграў гонку"
    assert "Крыніца" in item["preview"]


async def test_raw_queue_returns_collected_items(client):
    http, db = client
    # Insert a collected (untranslated) item
    await db.save_news_item(
        NewsItem(
            title="Breaking News",
            content="Some F1 content here.",
            url="https://example.com/raw",
            source="test",
            source_type=SourceType.RSS,
            published_at=datetime(2026, 7, 5, 12, 0),
            relevance_score=0.8,
        )
    )
    response = await http.get("/admin/api/queue/raw")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["has_translation"] is False
    assert item["status"] == "collected"
    assert "has_translation" in item


async def test_approve_moves_to_queued(client):
    http, db = client
    item_id = await seed_processed(db)
    response = await http.post(f"/admin/api/items/{item_id}/approve")
    assert response.status_code == 200
    assert (await db.get_item(item_id)).status == NewsStatus.QUEUED


async def test_approve_twice_conflicts(client):
    http, db = client
    item_id = await seed_processed(db)
    await http.post(f"/admin/api/items/{item_id}/approve")
    response = await http.post(f"/admin/api/items/{item_id}/approve")
    assert response.status_code == 409


async def test_reject(client):
    http, db = client
    item_id = await seed_processed(db)
    response = await http.post(f"/admin/api/items/{item_id}/reject")
    assert response.status_code == 200
    stored = await db.get_item(item_id)
    assert stored.status == NewsStatus.REJECTED


async def test_edit_updates_belarusian_fields(client):
    http, db = client
    item_id = await seed_processed(db)
    response = await http.post(
        f"/admin/api/items/{item_id}/edit",
        json={"title_be": "Новы загаловак", "summary": "Новы тэкст.", "tags": ["#тэст", "гонка"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title_be"] == "Новы загаловак"
    assert data["tags"] == ["тэст", "гонка"]  # hashes stripped
    assert "Новы загаловак" in data["preview"]


async def test_edit_nothing_400(client):
    http, db = client
    item_id = await seed_processed(db)
    response = await http.post(f"/admin/api/items/{item_id}/edit", json={})
    assert response.status_code == 400


async def test_edit_long_summary_doesnt_overflow(client):
    """Edit summary field must accept at least 4000 chars (full translated article)."""
    http, db = client
    item_id = await seed_processed(db)
    long_text = "Тэкст " * 800  # ~4800 chars
    response = await http.post(
        f"/admin/api/items/{item_id}/edit",
        json={"summary": long_text},
    )
    assert response.status_code == 200, f"Long summary rejected: {response.text}"


async def test_stats_shape(client):
    http, db = client
    await seed_processed(db)
    response = await http.get("/admin/api/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["pending"] == 1
    assert "max_posts_per_hour" in data


async def test_unauthorized_without_override():
    """Without the dependency override, requests need valid initData"""
    app = FastAPI()
    app.include_router(admin_api)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get("/admin/api/queue")
    assert response.status_code == 401


async def seed_raw(db, url, title="Ferrari reveals new Mexico upgrade", **kwargs):
    return await db.save_news_item(
        NewsItem(
            title=title,
            content="Article text " * 100,
            url=url,
            source="test",
            source_type=SourceType.WEB,
            published_at=datetime.utcnow(),
            **kwargs,
        )
    )


async def test_grouped_queue_pages_stories_and_preserves_all_articles(client):
    http, db = client
    original_url = "https://www.autosport.com/f1/news/ferrari-new-upgrade/12345/"
    original_id = await seed_raw(
        db, original_url, story_id="story-1", collection_info={"text_quality": "article"}
    )
    copy_id = await seed_raw(
        db,
        "https://www.planetf1.com/news/ferrari-new-upgrade",
        story_id="story-1",
        collection_info={
            "text_quality": "teaser",
            "references": [
                {
                    "url": original_url,
                    "source": "Autosport",
                    "kind": "attribution",
                    "evidence": "Reported by Autosport",
                }
            ],
        },
    )
    await seed_raw(db, "https://example.com/another-story", "Unrelated event", story_id="story-2")
    page = (await http.get("/admin/api/queue/raw?page_size=1")).json()
    assert page["total"] == 2
    assert page["total_articles"] == 3
    group = page["items"][0]
    assert group["id"] == original_id
    assert group["related_items"][0]["id"] == copy_id
    assert group["text_quality"]["needs_confirmation"] is False
    assert group["editorial_reasons"][0]["code"] == "source"
    second = (await http.get("/admin/api/queue/raw?page_size=1&page=1")).json()
    assert second["items"][0]["story_id"] == "story-2"
    assert (await http.get("/admin/api/queue/raw?page=-1")).status_code == 422
    # Moderating the original never discards the other article.
    await http.post(f"/admin/api/items/{original_id}/reject")
    updated = (await http.get("/admin/api/queue/raw?page_size=1")).json()
    assert updated["items"][0]["id"] == copy_id
    assert (await db.get_item(copy_id)).status == NewsStatus.COLLECTED


async def test_translation_requires_acknowledging_missing_full_text(client, monkeypatch):
    from unittest.mock import AsyncMock, Mock

    http, db = client
    item_id = await seed_raw(
        db, "https://example.com/teaser", collection_info={"text_quality": "teaser"}
    )
    processor = Mock(translate_news=AsyncMock())
    get_processor = AsyncMock(return_value=processor)
    monkeypatch.setattr(router_module, "get_content_processor", get_processor)
    blocked = await http.post(f"/admin/api/items/{item_id}/translate")
    assert blocked.status_code == 409
    assert "RSS-анонс" in blocked.json()["detail"]
    get_processor.assert_not_awaited()
    allowed = await http.post(f"/admin/api/items/{item_id}/translate?allow_incomplete=true")
    assert allowed.status_code == 200


async def test_original_fetch_checks_attribution_and_reuses_existing_item(client, monkeypatch):
    from unittest.mock import AsyncMock

    http, db = client
    original_url = "https://www.autosport.com/f1/news/ferrari-interview/12345/"
    copy_id = await seed_raw(
        db,
        "https://www.planetf1.com/news/ferrari-interview",
        collection_info={"references": [{"url": original_url, "kind": "attribution"}]},
    )
    original_id = await seed_raw(db, original_url)
    fetch = AsyncMock()
    monkeypatch.setattr("src.collectors.web_scraper.WebScraperCollector.fetch_reference", fetch)
    blocked = await http.post(
        f"/admin/api/items/{copy_id}/collect-original", json={"url": "https://127.0.0.1/private"}
    )
    assert blocked.status_code == 400
    fetch.assert_not_awaited()
    response = await http.post(
        f"/admin/api/items/{copy_id}/collect-original", json={"url": original_url}
    )
    assert response.status_code == 200
    fetch.assert_not_awaited()
    assert response.json()["id"] == original_id
    assert (await db.get_item(copy_id)).story_id == (await db.get_item(original_id)).story_id


async def test_original_fetch_saves_evidence_without_starting_ai(client, monkeypatch):
    from unittest.mock import AsyncMock

    http, db = client
    original_url = "https://www.the-race.com/formula-1/ferrari-exclusive-interview/"
    copy_id = await seed_raw(
        db,
        "https://www.planetf1.com/news/copy-interview",
        collection_info={"references": [{"url": original_url, "kind": "attribution"}]},
    )
    fetched = NewsItem(
        title="Ferrari exclusive interview",
        content="Original content " * 100,
        url=original_url,
        source="The Race",
        source_type=SourceType.WEB,
        published_at=datetime.utcnow(),
        collection_info={"text_quality": "article"},
    )
    monkeypatch.setattr(
        "src.collectors.web_scraper.WebScraperCollector.fetch_reference",
        AsyncMock(return_value=fetched),
    )
    processor = AsyncMock()
    monkeypatch.setattr(router_module, "get_content_processor", processor)
    response = await http.post(
        f"/admin/api/items/{copy_id}/collect-original", json={"url": original_url}
    )
    assert response.status_code == 200
    stored = await db.get_item(response.json()["id"])
    assert stored.collection_info["text_quality"] == "article"
    assert stored.status == NewsStatus.COLLECTED
    assert stored.story_id == (await db.get_item(copy_id)).story_id
    processor.assert_not_awaited()


async def test_legacy_metadata_is_unknown_and_null_story_ids_remain_visible(client):
    from sqlalchemy import update

    from src.database import NewsItemDB

    http, db = client
    await seed_raw(db, "https://example.com/legacy-article")
    async with db.session() as session:
        await session.execute(update(NewsItemDB).values(story_id=None, collection_info=None))
        await session.commit()
    response = await http.get("/admin/api/queue/raw")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["text_quality"]["status"] == "unknown"
    assert data["items"][0]["story_id"]
