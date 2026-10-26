"""
Message formatting for the Telegram bot — pure functions, no I/O.
"""

from ..models import NewsStatus, ProcessedNewsItem

STATUS_LABELS = {
    NewsStatus.COLLECTED: "🆕 собрано",
    NewsStatus.PROCESSED: "⏳ ждёт модерации",
    NewsStatus.QUEUED: "📤 в очереди на публикацию",
    NewsStatus.PUBLISHED: "✅ опубликовано",
    NewsStatus.REJECTED: "❌ отклонено",
}


def format_channel_post(item: ProcessedNewsItem) -> str:
    """The post exactly as it goes to the channel — Belarusian output"""
    title = item.translated_title or item.title
    message = f"🏎️ {title}\n\n"
    if item.key_points:
        message += "🔑 Галоўнае:\n"
        for point in item.key_points[:3]:
            message += f"• {point}\n"
        message += "\n"
    if item.translated_summary:
        body = item.translated_summary
    elif item.summary:
        body = item.summary
    else:
        body = ""
    if body:
        message += f"{body}\n\n"
    message += f"📰 Крыніца: {item.source}\n"
    message += f"🔗 Чытаць: {item.url}"
    if item.tags:
        tags_str = " ".join([f"#{t.replace(' ', '_')}" for t in item.tags[:3]])
        message += f"\n\n{tags_str}"
    # Telegram hard limit: 4096 chars
    if len(message) > 4096:
        message = message[:4093] + "..."
    return message


def format_details(item: ProcessedNewsItem) -> str:
    """Admin-facing detail view of one item"""
    message = "📰 Детали новости:\n\n"
    if item.translated_title:
        message += f"Заголовок (BY): {item.translated_title}\n"
    message += f"Заголовок (оригинал): {item.title}\n\n"
    if item.summary:
        message += f"Краткое содержание:\n{item.summary}\n\n"
    if item.key_points:
        message += "Ключевые моменты:\n"
        for i, point in enumerate(item.key_points, 1):
            message += f"{i}. {point}\n"
        message += "\n"
    message += f"Статус: {STATUS_LABELS.get(item.status, item.status)}\n"
    message += f"Источник: {item.source}\n"
    message += f"URL: {item.url}\n"
    message += f"Релевантность: {item.relevance_score:.2f}\n"
    message += f"Важность: {item.importance_level}/5\n"
    message += f"Настроение: {item.sentiment}\n"
    if item.tags:
        message += f"Теги: {', '.join(item.tags)}\n"
    if item.rejected_reason:
        message += f"Причина отклонения: {item.rejected_reason}\n"
    message += f"Дата публикации источника: {item.published_at:%d.%m.%Y %H:%M}\n"
    return message


def format_queue_page(items: list[ProcessedNewsItem], page: int, total: int) -> str:
    """One page of the moderation queue"""
    if total == 0:
        return "📋 Очередь модерации пуста."

    message = f"📋 Очередь модерации — {total} новост(ей), страница {page + 1}:\n\n"
    for i, item in enumerate(items, start=1):
        title = item.title[:80] + "..." if len(item.title) > 80 else item.title
        message += f"{i}. {title}\n"
        message += (
            f"   Источник: {item.source} | "
            f"Релевантность: {item.relevance_score:.2f} | "
            f"Важность: {item.importance_level}/5\n\n"
        )
    message += "Выберите новость кнопкой ниже."
    return message


def format_published_list(items: list[ProcessedNewsItem]) -> str:
    """Recently published items"""
    if not items:
        return "📰 Пока ничего не опубликовано."

    message = "📰 Последние публикации:\n\n"
    for i, item in enumerate(items, start=1):
        title = item.title[:80] + "..." if len(item.title) > 80 else item.title
        when = (
            f"{item.published_to_channel_at:%d.%m %H:%M}" if item.published_to_channel_at else "—"
        )
        message += f"{i}. {title}\n   {when} | {item.source}\n\n"
    return message


def format_status(
    stats, pending: int, queued: int, published_last_hour: int, max_per_hour: int
) -> str:
    """The /status message"""
    message = "📊 Статус системы\n\n"
    message += f"Всего собрано: {stats.total_collected}\n"
    for status, count in sorted(stats.by_status.items()):
        label = STATUS_LABELS.get(NewsStatus(status), status)
        message += f"  {label}: {count}\n"
    message += f"\n⏳ Ждут модерации: {pending}\n"
    message += f"📤 В очереди на публикацию: {queued}\n"
    message += f"🚦 Лимит публикаций: {published_last_hour}/{max_per_hour} за последний час\n"
    message += f"\n📅 Сегодня опубликовано: {stats.published_today}\n"
    message += f"📅 За неделю: {stats.published_this_week}\n"
    if stats.last_collection_time:
        message += f"\n🕐 Последний сбор: {stats.last_collection_time:%d.%m.%Y %H:%M} UTC"
    return message
