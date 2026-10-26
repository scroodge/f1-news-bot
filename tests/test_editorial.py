"""Editorial ordering, conservative dedup and persistence boundaries."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from src.collectors.news_collector import NewsCollector
from src.database import DatabaseManager
from src.editorial import canonical_url, editorial_priority, editorial_priority_sql
from src.models import NewsItem, SourceType


def item(url, title="F1 team reveals upgrade", content="Technical analysis"):
    return NewsItem(
        url=url,
        title=title,
        content=content,
        source="test",
        source_type=SourceType.RSS,
        published_at=datetime(2026, 10, 26),
    )


def test_tracking_removed_but_identity_preserved():
    assert canonical_url("https://www.autosport.com/f1/news/x/?id=7&utm_source=RSS#top") == (
        "https://www.autosport.com/f1/news/x/?id=7"
    )


def test_exclusive_word_alone_does_not_raise_priority():
    original = item("https://www.autosport.com/f1/news/x/", "Exclusive F1 news")
    assert editorial_priority(original) == 4
    original.content = "Speaking exclusively to us about the new car"
    assert editorial_priority(original) == 6
    original.content = "According to reports, there is an exclusive interview elsewhere"
    assert editorial_priority(original) == 4  # mixed signals cancel
    assert editorial_priority(item("https://www.autosport.com.evil.test/x")) == 0


async def test_url_dedup_preserves_publications_for_story_grouping(monkeypatch):
    collector = NewsCollector.__new__(NewsCollector)
    collector.collectors = {"rss": object(), "web": object()}
    copy = item("https://example.com/copy")
    original = item("https://www.the-race.com/formula-1/original")
    different = item("https://example.com/different", "F1 team delays upgrade")
    collector._collect_from_source = AsyncMock(side_effect=[[copy], [original, different]])
    save = AsyncMock(return_value="id")
    monkeypatch.setattr("src.collectors.news_collector.db_manager.save_news_item", save)
    monkeypatch.setattr(
        "src.collectors.news_collector.db_manager.get_story_candidates", AsyncMock(return_value=[])
    )
    collected = await collector.collect_all_news()
    assert [i.url for i in collected] == [original.url, copy.url, different.url]
    assert original.story_id == copy.story_id
    assert original.story_id != different.story_id
    assert save.await_count == 3


async def test_priority_is_applied_before_pagination_and_old_news_stays_below():
    from sqlalchemy import select

    from src.database import NewsItemDB

    db = DatabaseManager("sqlite+aiosqlite://")
    await db.create_tables()
    try:
        old = item(
            "https://www.the-race.com/formula-1/old", "Old interview", "Speaking exclusively"
        )
        old.created_at = datetime.utcnow() - timedelta(days=2)
        fresh_copy = item("https://example.com/new", "Latest copy")
        fresh_original = item(
            "https://www.autosport.com/f1/news/new/", "Original interview", "Speaking exclusively"
        )
        for news in [old, fresh_copy, fresh_original]:
            await db.save_news_item(news)
        # save_news_item sets created_at itself; adjust the old row explicitly.
        async with db.session() as session:
            row = (
                await session.execute(select(NewsItemDB).where(NewsItemDB.url == old.url))
            ).scalar_one()
            row.created_at = old.created_at
            await session.commit()
        first = await db.get_collected_news(limit=1)
        second = await db.get_collected_news(limit=1, offset=1)
        assert first[0].url == fresh_original.url
        assert second[0].url == fresh_copy.url
        async with db.session() as session:
            rows = (
                await session.execute(select(NewsItemDB, editorial_priority_sql(NewsItemDB)))
            ).all()
            for row, sql_score in rows:
                assert sql_score == editorial_priority(row)
    finally:
        await db.close()


async def test_sql_priority_matches_python_for_http_urls():
    from sqlalchemy import select

    from src.database import NewsItemDB

    db = DatabaseManager("sqlite+aiosqlite://")
    await db.create_tables()
    try:
        await db.save_news_item(item("http://www.autosport.com/f1/news/plain/", "Plain http"))
        async with db.session() as session:
            row, sql_score = (
                await session.execute(select(NewsItemDB, editorial_priority_sql(NewsItemDB)))
            ).one()
        assert sql_score == editorial_priority(row) == 4
    finally:
        await db.close()


async def test_story_grouping_failure_still_saves_items(monkeypatch):
    collector = NewsCollector.__new__(NewsCollector)
    collector.collectors = {"rss": object()}
    collector._collect_from_source = AsyncMock(return_value=[item("https://example.com/a")])
    save = AsyncMock(return_value="id")
    monkeypatch.setattr("src.collectors.news_collector.db_manager.save_news_item", save)
    monkeypatch.setattr(
        "src.collectors.news_collector.db_manager.get_story_candidates",
        AsyncMock(side_effect=RuntimeError("db down")),
    )
    await collector.collect_all_news()
    assert save.await_count == 1
