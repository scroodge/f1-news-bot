"""Tests for `/api/news` endpoint in FastAPI app"""

from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

import src.main as main_module
from src.database import DatabaseManager
from src.models import NewsItem, ProcessedNewsItem, SourceType


@pytest.fixture
async def client(monkeypatch):
    db = DatabaseManager("sqlite+aiosqlite://")
    await db.create_tables()
    monkeypatch.setattr(main_module, "db_manager", db)

    app = main_module.app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, db
    await db.close()


async def test_get_news_all_and_filtered(client):
    http, db = client

    # Seed items
    item1 = NewsItem(
        title="News Item 1",
        content="Content 1",
        url="https://example.com/1",
        source="rss",
        source_type=SourceType.RSS,
        published_at=datetime(2026, 7, 5, 12, 0),
        relevance_score=0.9,
    )
    item2 = NewsItem(
        title="News Item 2",
        content="Content 2",
        url="https://example.com/2",
        source="rss",
        source_type=SourceType.RSS,
        published_at=datetime(2026, 7, 5, 12, 5),
        relevance_score=0.9,
    )

    id1 = await db.save_news_item(item1)
    id2 = await db.save_news_item(item2)

    await db.mark_processed(
        id2,
        ProcessedNewsItem(
            id=id2,
            title="News Item 2",
            content="Content 2",
            url="https://example.com/2",
            source="rss",
            source_type=SourceType.RSS,
            published_at=datetime(2026, 7, 5, 12, 5),
            summary="Summary 2",
            key_points=[],
            importance_level=1,
            tags=[],
        ),
    )

    # Test GET /api/news without status filter
    response = await http.get("/api/news")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["news_items"]) == 2

    # Test GET /api/news with status=collected
    response_collected = await http.get("/api/news?status=collected")
    assert response_collected.status_code == 200
    data_collected = response_collected.json()
    assert data_collected["count"] == 1
    assert data_collected["news_items"][0]["id"] == id1

    # Test GET /api/news with status=processed
    response_processed = await http.get("/api/news?status=processed")
    assert response_processed.status_code == 200
    data_processed = response_processed.json()
    assert data_processed["count"] == 1
    assert data_processed["news_items"][0]["id"] == id2
