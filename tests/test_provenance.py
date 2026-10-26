"""Evidence must distinguish article citations from navigation and teaser length."""

from types import SimpleNamespace

import pytest

from src.provenance import article_url, quality_info, references_from_html, text_evidence

ORIGINAL = "https://www.autosport.com/f1/news/ferrari-new-upgrade/123456/"


def test_attribution_keeps_article_link_and_evidence_but_not_related_links():
    html = f'''<html><nav><p>Reported by <a href="{ORIGINAL}">Autosport</a></p></nav>
    <article><p>According to <a href="{ORIGINAL}?utm_source=copy">Autosport</a>, Ferrari has a new upgrade.</p>
    <p>Read next: <a href="https://www.the-race.com/formula-1/another-ferrari-story/">Ferrari</a></p>
    <p>According to <a href="https://www.autosport.com/">Autosport homepage</a></p></article></html>'''
    refs = references_from_html(html, "https://www.planetf1.com/news/ferrari-update")
    assert len(refs) == 1
    assert refs[0]["url"] == ORIGINAL
    assert "According to" in refs[0]["evidence"]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/a-long-article",
        "https://www.autosport.com.evil.test/a-long-article",
        "https://www.autosport.com:8443/f1/news/a-long-article",
        "https://user@www.autosport.com/f1/news/a-long-article",
        "https://www.autosport.com/f1/news/",
        "javascript:alert(1)",
    ],
)
def test_reference_fetch_rejects_untrusted_or_listing_urls(url):
    assert not article_url(url)


def test_long_rss_teaser_is_still_a_teaser_and_paywall_metadata_wins():
    text = "Some F1 news " * 150
    assert text_evidence(text, "rss_summary")["text_quality"] == "teaser"
    assert text_evidence(text, "article")["text_quality"] == "article"
    html = '<script type="application/ld+json">{"@type":"NewsArticle","isAccessibleForFree":false}</script>'
    assert text_evidence(text, "article", html)["text_quality"] == "paywall"
    assert text_evidence("Subscribe to continue reading", "article")["text_quality"] == "paywall"
    assert text_evidence("Brief F1 news", "article")["text_quality"] == "short"
    assert (
        quality_info(SimpleNamespace(content="legacy", collection_info={}))["needs_confirmation"]
        is True
    )


def test_named_attribution_without_a_link_does_not_invent_an_article_url():
    from src.provenance import named_attributions

    text = "According to Autosport, Ferrari is changing its plans."
    refs = named_attributions(text, "https://www.planetf1.com/news/new-plans")
    assert refs[0]["source"] == "autosport.com"
    assert "url" not in refs[0]
    assert named_attributions(text, "https://www.autosport.com/f1/news/new-plans") == []
    assert article_url("https://www.bbc.com/sport/formula1/articles/c1234567890")
