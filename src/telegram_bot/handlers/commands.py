"""
Command handlers: /start /help /status /queue /view /publish /published
All state comes from PostgreSQL — nothing is held in memory.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ...config import settings
from ...database import db_manager
from ...models import NewsStatus
from ..formatting import format_details, format_published_list, format_queue_page, format_status
from .helpers import admin_only, get_queue_page, item_keyboard, queue_keyboard

logger = logging.getLogger(__name__)


@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = await db_manager.count_by_status(NewsStatus.PROCESSED)
    message = (
        "🏎️ F1 News Bot — панель модерации\n\n"
        f"⏳ Новостей ждут модерации: {pending}\n\n"
        "Команды: /queue — очередь, /status — статус, /help — справка"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📋 Очередь", callback_data="queue_0"),
                InlineKeyboardButton("📊 Статус", callback_data="status_refresh"),
            ]
        ]
    )
    await update.message.reply_text(message, reply_markup=keyboard)


@admin_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "📚 Справка\n\n"
        "/queue — очередь модерации (одобрить/отклонить/посмотреть)\n"
        "/view <номер> — детали новости из очереди\n"
        "/publish <номер> — одобрить новость из очереди\n"
        "/published — последние публикации\n"
        "/status — статистика системы\n\n"
        "Одобренные новости публикуются автоматически с учётом лимита "
        f"({settings.max_posts_per_hour} в час)."
    )
    await update.message.reply_text(message)


@admin_only
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = await db_manager.get_stats()
    pending = await db_manager.count_by_status(NewsStatus.PROCESSED)
    queued = await db_manager.count_by_status(NewsStatus.QUEUED)
    last_hour = await db_manager.published_in_last_hour()
    message = format_status(stats, pending, queued, last_hour, settings.max_posts_per_hour)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔄 Обновить", callback_data="status_refresh")]]
    )
    await update.message.reply_text(message, reply_markup=keyboard)


@admin_only
async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items, total = await get_queue_page(page=0)
    message = format_queue_page(items, page=0, total=total)
    await update.message.reply_text(message, reply_markup=queue_keyboard(items, 0, total))


async def _nth_queue_item(n: int):
    """1-based item lookup in the moderation queue"""
    items = await db_manager.get_by_status(NewsStatus.PROCESSED, limit=1, offset=n - 1)
    return items[0] if items else None


@admin_only
async def view_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Использование: /view <номер новости из /queue>")
        return
    item = await _nth_queue_item(int(context.args[0]))
    if item is None:
        await update.message.reply_text("❌ Новость с таким номером не найдена в очереди")
        return
    await update.message.reply_text(format_details(item), reply_markup=item_keyboard(item.id))


@admin_only
async def publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Использование: /publish <номер новости из /queue>")
        return
    item = await _nth_queue_item(int(context.args[0]))
    if item is None:
        await update.message.reply_text("❌ Новость с таким номером не найдена в очереди")
        return
    if await db_manager.approve(item.id):
        await update.message.reply_text(
            f"✅ Одобрено: {item.title[:80]}\n"
            "Будет опубликовано автоматически (с учётом лимита в час)."
        )
    else:
        await update.message.reply_text("❌ Не удалось одобрить (возможно, статус уже изменился)")


@admin_only
async def published_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = await db_manager.get_by_status(NewsStatus.PUBLISHED, limit=10)
    await update.message.reply_text(format_published_list(items))
