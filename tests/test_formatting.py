"""Tests for bot message formatting"""

from datetime import datetime

from src.models import NewsStatus, ProcessedNewsItem, SourceType, Stats
from src.telegram_bot.formatting import (
    format_channel_post,
    format_details,
    format_published_list,
    format_queue_page,
    format_status,
)


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


def test_channel_post_shows_full_text_within_limit():
    long_text = "слова " * 100  # 600 chars
    post = format_channel_post(make_item(summary=long_text))
    assert "слова" in post
    assert len(post) <= 4096  # safety truncation


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


def test_published_list_empty():
    assert format_published_list([]) == "📰 Пока ничего не опубликовано."


def test_published_list_with_items():
    items = [
        make_item(
            title="First published item",
            published_to_channel_at=datetime(2026, 7, 5, 14, 0),
        ),
        make_item(title="Second published item", published_to_channel_at=None),
    ]
    formatted = format_published_list(items)
    assert "1. First published item" in formatted
    assert "05.07 14:00 | autosport.com" in formatted
    assert "2. Second published item" in formatted
    assert "— | autosport.com" in formatted


def test_format_status_full():
    stats = Stats(
        total_collected=10,
        by_status={
            NewsStatus.COLLECTED: 2,
            NewsStatus.PROCESSED: 3,
            NewsStatus.PUBLISHED: 5,
        },
        published_today=5,
        published_this_week=20,
        last_collection_time=datetime(2026, 7, 5, 14, 30),
    )
    result = format_status(stats, pending=3, queued=1, published_last_hour=2, max_per_hour=5)

    assert "📊 Статус системы" in result
    assert "Всего собрано: 10" in result
    assert "🆕 собрано: 2" in result
    assert "⏳ ждёт модерации: 3" in result
    assert "✅ опубликовано: 5" in result
    assert "⏳ Ждут модерации: 3" in result
    assert "📤 В очереди на публикацию: 1" in result
    assert "🚦 Лимит публикаций: 2/5 за последний час" in result
    assert "📅 Сегодня опубликовано: 5" in result
    assert "📅 За неделю: 20" in result
    assert "🕐 Последний сбор: 05.07.2026 14:30 UTC" in result


def test_format_status_no_last_collection_time():
    stats = Stats(
        total_collected=0,
        by_status={},
        published_today=0,
        published_this_week=0,
        last_collection_time=None,
    )
    result = format_status(stats, pending=0, queued=0, published_last_hour=0, max_per_hour=5)

    assert "📊 Статус системы" in result
    assert "Всего собрано: 0" in result
    assert "Последний сбор" not in result


def test_format_status_unknown_status_fallback():
    stats = Stats(
        total_collected=1,
        by_status={"custom_status": 1},
        published_today=0,
        published_this_week=0,
    )
    result = format_status(stats, pending=0, queued=0, published_last_hour=0, max_per_hour=5)

    assert "custom_status: 1" in result
