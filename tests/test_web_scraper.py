"""Tests for the web scraper collector (offline — fixture HTML, no network)"""

from src.collectors.web_scraper import (
    AUTO_DISABLE_AFTER_FAILURES,
    ScrapeSource,
    SourceHealth,
    WebScraperCollector,
    extract_article,
    extract_article_links,
    load_sources,
)

LISTING_HTML = """
<html><body>
  <a href="/f1/news/verstappen-pole-silverstone">Verstappen pole</a>
  <a href="https://www.example.com/f1/news/ferrari-upgrade/">Ferrari upgrade</a>
  <a href="/f1/news/verstappen-pole-silverstone">duplicate link</a>
  <a href="/f1/schedule/">not an article</a>
  <a href="https://other-site.com/f1/news/external">external host</a>
  <a href="/f1/news/">the listing itself</a>
  <a href="mailto:tips@example.com">mail</a>
</body></html>
"""

ARTICLE_HTML = """
<html>
<head>
  <title>Verstappen takes pole position at Silverstone</title>
  <meta property="og:image" content="https://www.example.com/img/pole.jpg">
</head>
<body>
<article>
  <h1>Verstappen takes pole position at Silverstone</h1>
  <p>Max Verstappen took pole position for the British Grand Prix on Saturday,
  beating Lando Norris by just a tenth of a second in a thrilling qualifying
  session at Silverstone. Charles Leclerc could only manage seventh for Ferrari
  after struggling with balance throughout the session.</p>
  <p>The result puts Verstappen in a strong position for Sunday's race, where
  strategy and tyre management are expected to play a decisive role.</p>
</article>
</body></html>
"""


def test_extract_article_links_filters_and_dedups():
    links = extract_article_links(LISTING_HTML, "https://www.example.com/f1/news/", "/f1/news/")
    assert links == [
        "https://www.example.com/f1/news/verstappen-pole-silverstone",
        "https://www.example.com/f1/news/ferrari-upgrade/",
    ]


def test_extract_article_full_text():
    article = extract_article(ARTICLE_HTML, "https://www.example.com/f1/news/pole")
    assert article is not None
    assert "pole position" in article["title"].lower()
    assert "tenth of a second" in article["text"]  # full text, not a snippet


def test_extract_article_rejects_empty():
    assert extract_article("<html><body></body></html>", "https://x.example/") is None


def test_load_sources_from_yaml():
    sources = load_sources()
    assert len(sources) >= 5
    names = {s.name for s in sources}
    assert "formula1.com" in names
    assert all(s.max_articles > 0 for s in sources)


def test_health_auto_disable():
    health = SourceHealth()
    for _ in range(AUTO_DISABLE_AFTER_FAILURES - 1):
        health.record_failure("boom")
    assert not health.disabled
    health.record_failure("boom")
    assert health.disabled
    assert health.error_streak == AUTO_DISABLE_AFTER_FAILURES


def test_health_success_resets_streak():
    health = SourceHealth()
    health.record_failure("boom")
    health.record_success()
    assert health.error_streak == 0
    assert health.last_error is None
    assert health.last_success is not None


def test_collector_health_report():
    collector = WebScraperCollector(
        sources=[
            ScrapeSource(name="test", list_url="https://x.example/news", link_pattern="/news/")
        ]
    )
    report = collector.get_health_report()
    assert "test" in report
    assert report["test"]["disabled"] is False
    assert report["test"]["error_streak"] == 0
