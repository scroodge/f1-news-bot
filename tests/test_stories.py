"""Story grouping is bounded by time, evidence and headline similarity."""

from datetime import datetime, timedelta

from src.models import NewsItem, SourceType
from src.stories import assign_stories, representative, same_story


def news(title, url="https://example.com/news", **kw):
    return NewsItem(
        title=title,
        url=url,
        source="test",
        source_type=SourceType.WEB,
        content="F1 news",
        published_at=datetime(2026, 10, 26, 12),
        **kw,
    )


def test_cited_original_groups_different_titles_and_is_selected():
    original = news(
        "An exclusive Ferrari interview",
        "https://www.autosport.com/f1/news/a-ferrari-interview/12345/",
    )
    copy = news(
        "Ferrari boss reveals radical new plan",
        collection_info={"references": [{"url": original.url, "kind": "attribution"}]},
    )
    assign_stories([copy, original], [])
    assert copy.story_id == original.story_id
    assert representative([copy, original]) is original


def test_similar_headlines_group_but_unrelated_developments_do_not():
    first = news("Ferrari reveals new front wing upgrade ahead of Mexico GP")
    second = news("Ferrari reveals front wing upgrade for Mexico GP", "https://other.com/news")
    assert same_story(first, second)
    unrelated = news(
        "Ferrari delays new front wing upgrade ahead of Mexico GP", "https://third.com/news"
    )
    assert not same_story(first, unrelated)
    # A changed action may be a distinct development even with most words shared.
    negated = news(
        "Ferrari will not reveal front wing upgrade for Mexico GP", "https://third.com/other"
    )
    assert not same_story(second, negated)
    another_race = news(
        "Ferrari reveals front wing upgrade for Brazil GP", "https://other.com/another"
    )
    assert not same_story(second, another_race)
    another_driver = news(
        "Leclerc reacts to surprise Ferrari decision ahead of Mexico GP", "https://other.com/l"
    )
    driver = news("Hamilton reacts to surprise Ferrari decision ahead of Mexico GP")
    assert not same_story(driver, another_driver)
    unrelated.published_at += timedelta(days=3)
    assert not same_story(first, unrelated)


def test_group_membership_survives_later_collection_cycle():
    existing = news("Ferrari reveals front wing upgrade for Mexico GP", story_id="existing")
    new = news("Ferrari reveals new front wing upgrade ahead of Mexico GP", "https://other.com/new")
    assign_stories([new], [existing])
    assert new.story_id == "existing"
