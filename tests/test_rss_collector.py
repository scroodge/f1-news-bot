"""RSS summaries must not prevent fetching original articles."""

from unittest.mock import AsyncMock, Mock

from src.collectors.rss_collector import RSSCollector


async def test_long_teaser_fetches_full_text_and_known_urls_are_skipped(monkeypatch):
    teaser = "A Formula 1 Ferrari update. " * 30
    full = "An original Formula 1 technical analysis. " * 60
    xml = f"""<rss version="2.0"><channel><title>F1</title>
      <item><title>Ferrari F1 update</title>
      <link>https://example.com/f1/new?utm_source=rss</link>
      <description>{teaser}</description></item>
      <item><title>Ferrari F1 old update</title>
      <link>https://example.com/f1/known</link>
      <description>{teaser}</description></item>
    </channel></rss>"""
    response = Mock(status=200, text=AsyncMock(return_value=xml))
    context = AsyncMock()
    context.__aenter__.return_value = response
    collector = RSSCollector()
    collector.session = Mock(get=Mock(return_value=context))
    collector._fetch_full_text = AsyncMock(return_value=full)
    known = AsyncMock(side_effect=lambda url: url.endswith("/known"))
    monkeypatch.setattr("src.database.db_manager.url_exists", known)
    items = await collector._collect_from_feed("https://example.com/rss")
    assert len(items) == 1
    assert items[0].url == "https://example.com/f1/new"
    assert items[0].content == full
    collector._fetch_full_text.assert_awaited_once_with("https://example.com/f1/new")


async def test_long_teaser_without_article_keeps_quality_warning(monkeypatch):
    teaser = "Ferrari Formula 1 news. " * 60
    xml = f"""<rss version="2.0"><channel><title>F1</title><item>
    <title>Ferrari F1</title><link>https://example.com/f1/new</link>
    <description>{teaser}</description></item></channel></rss>"""
    context = AsyncMock()
    context.__aenter__.return_value = Mock(status=200, text=AsyncMock(return_value=xml))
    collector = RSSCollector()
    collector.session = Mock(get=Mock(return_value=context))
    collector._fetch_full_text = AsyncMock(return_value=None)
    monkeypatch.setattr("src.database.db_manager.url_exists", AsyncMock(return_value=False))
    items = await collector._collect_from_feed("https://example.com/rss")
    assert items[0].collection_info["text_quality"] == "teaser"
    assert len(items[0].content) > 800


def _robots_session(status=None, error=None):
    context = AsyncMock()
    if error:
        context.__aenter__.side_effect = error
    else:
        context.__aenter__.return_value = Mock(status=status, text=AsyncMock(return_value=""))
    return Mock(get=Mock(return_value=context))


async def test_unreachable_robots_disallows_until_next_cycle():
    collector = RSSCollector()
    collector.session = _robots_session(status=503)
    assert await collector._fetch_full_text("https://example.com/f1/a") is None
    assert await collector._fetch_full_text("https://example.com/f1/b") is None
    # One robots.txt request per host per cycle, not one per article
    assert collector.session.get.call_count == 1
    collector.session = _robots_session(error=OSError("down"))
    collector._robots = {}
    assert await collector._load_robots("example.com") is False


async def test_missing_robots_allows_fetch():
    collector = RSSCollector()
    collector.session = _robots_session(status=404)
    assert await collector._load_robots("example.com") is None


async def test_robots_cache_is_reset_each_cycle():
    collector = RSSCollector()
    collector.session = Mock()
    collector.feeds = []
    collector._robots = {"example.com": False}
    await collector.collect_news()
    assert collector._robots == {}
