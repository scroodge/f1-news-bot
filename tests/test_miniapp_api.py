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
