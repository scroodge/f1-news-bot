"""Tests for bot message formatting"""

from datetime import datetime

from src.models import ProcessedNewsItem, SourceType
from src.telegram_bot.formatting import format_channel_post, format_details, format_queue_page


def make_item(**overrides) -> ProcessedNewsItem:
    defaults = dict(
        id="00000000-0000-0000-0000-000000000001",
        title="Verstappen wins the British Grand Prix",
        content="Full article text.",
        url="https://example.com/news/1",
        source="autosport.com",
        source_type=SourceType.RSS,
        published_at=datetime(2026, 7, 5, 12, 0),
        summary="Макс Ферстапен перамог на Сільверстоўне.",
        key_points=["поўл-пазіцыя", "хуткі круг", "трэцяя перамога запар", "чацвёрты пункт"],
        importance_level=4,
        relevance_score=0.95,
        tags=["гонка", "ферстапен"],
        translated_title="Ферстапен выйграў Гран-пры Вялікабрытаніі",
    )
    defaults.update(overrides)
    return ProcessedNewsItem(**defaults)


def test_channel_post_uses_belarusian_title():
    post = format_channel_post(make_item())
    assert "Ферстапен выйграў" in post
    assert "Verstappen wins" not in post


def test_channel_post_belarusian_labels():
    post = format_channel_post(make_item())
    assert "Крыніца: autosport.com" in post
    assert "Чытаць: https://example.com/news/1" in post
    assert "#гонка" in post


def test_channel_post_falls_back_to_original_title():
    post = format_channel_post(make_item(translated_title=None))
    assert "Verstappen wins the British Grand Prix" in post


def test_channel_post_limits_key_points():
    post = format_channel_post(make_item())
    assert "поўл-пазіцыя" in post
    assert "чацвёрты пункт" not in post  # only first 3 key points


def test_channel_post_full_summary():
    post = format_channel_post(make_item(summary="х" * 500))
    assert "х" * 500 in post  # full summary, no truncation


def test_details_show_both_titles():
    details = format_details(make_item())
    assert "Ферстапен выйграў" in details
    assert "Verstappen wins" in details
    assert "0.95" in details
    assert "4/5" in details


def test_queue_page_empty():
    assert "пуста" in format_queue_page([], page=0, total=0)


def test_queue_page_lists_items():
    items = [make_item(), make_item(title="Ferrari upgrade package")]
    page = format_queue_page(items, page=0, total=2)
    assert "1." in page and "2." in page
