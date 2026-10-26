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
