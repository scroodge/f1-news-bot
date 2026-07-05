"""Tests for bot message formatting"""

from datetime import datetime

from src.models import ProcessedNewsItem, SourceType
from src.telegram_bot.formatting import format_channel_post, format_details, format_queue_page


def make_item(**overrides) -> ProcessedNewsItem:
    defaults = dict(
        id="00000000-0000-0000-0000-000000000001",
        title="Ферстаппен выиграл Гран-при Великобритании",
        content="Полный текст новости.",
        url="https://example.com/news/1",
        source="f1news.ru",
        source_type=SourceType.RSS,
        published_at=datetime(2026, 7, 5, 12, 0),
        summary="Макс Ферстаппен одержал победу на Сильверстоуне.",
        key_points=["поул-позиция", "быстрый круг", "третья победа подряд"],
        importance_level=4,
        relevance_score=0.95,
        tags=["гонка", "верстаппен"],
    )
    defaults.update(overrides)
    return ProcessedNewsItem(**defaults)


def test_channel_post_contains_essentials():
    post = format_channel_post(make_item())
    assert "Ферстаппен выиграл" in post
    assert "https://example.com/news/1" in post
    assert "f1news.ru" in post
    assert "#гонка" in post


def test_channel_post_limits_key_points():
    post = format_channel_post(make_item())
    assert "поул-позиция" in post
    assert "быстрый круг" in post
    assert "третья победа подряд" not in post  # only first 2 key points


def test_channel_post_truncates_long_summary():
    post = format_channel_post(make_item(summary="х" * 300))
    assert "х" * 200 + "..." in post


def test_details_show_score_and_status():
    details = format_details(make_item())
    assert "0.95" in details
    assert "4/5" in details


def test_queue_page_empty():
    assert "пуста" in format_queue_page([], page=0, total=0)


def test_queue_page_lists_items():
    items = [make_item(), make_item(title="Феррари обновила болид")]
    page = format_queue_page(items, page=0, total=2)
    assert "1." in page and "2." in page
    assert "Феррари обновила болид" in page
