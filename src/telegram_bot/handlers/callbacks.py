"""
Inline-button callback handlers.

callback_data grammar:
  queue_<page>        show queue page
  view_<id>           item details
  approve_<id>        processed -> queued
  reject_<id>         -> rejected
  delete_<id>         remove from DB entirely
  rejectall_confirm   ask confirmation
  rejectall_yes / rejectall_no
  status_refresh      re-render /status
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from ...config import settings
from ...database import db_manager
from ...models import NewsStatus
from ..formatting import format_details, format_queue_page, format_status
from .helpers import admin_only, get_queue_page, item_keyboard, queue_keyboard

logger = logging.getLogger(__name__)

_BACK_TO_QUEUE = InlineKeyboardMarkup(
    [[InlineKeyboardButton("📋 К очереди", callback_data="queue_0")]]
)


async def _safe_edit(query, text, reply_markup=None):
    """edit_message_text that tolerates 'message is not modified'"""
    try:
        await query.edit_message_text(text, parse_mode=None, reply_markup=reply_markup)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


@admin_only
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    try:
        if data.startswith("queue_"):
            await _show_queue(query, page=int(data.removeprefix("queue_")))
        elif data.startswith("view_"):
            await _show_item(query, data.removeprefix("view_"))
        elif data.startswith("approve_"):
            await _approve(query, data.removeprefix("approve_"))
        elif data.startswith("reject_"):
            await _reject(query, data.removeprefix("reject_"))
        elif data.startswith("delete_"):
            await _delete(query, data.removeprefix("delete_"))
        elif data == "rejectall_confirm":
            await _reject_all_confirm(query)
        elif data == "rejectall_yes":
            await _reject_all(query)
        elif data == "rejectall_no":
            await _show_queue(query, page=0)
        elif data == "status_refresh":
            await _show_status(query)
        else:
            logger.warning(f"Unknown callback data: {data}")
    except Exception as e:
        logger.error(f"Error handling callback '{data}': {e}", exc_info=True)
        await _safe_edit(query, "❌ Ошибка обработки действия", reply_markup=_BACK_TO_QUEUE)


async def _show_queue(query, page: int):
    items, total = await get_queue_page(page)
    if not items and page > 0:  # page emptied by moderation — go back a page
        page = 0
        items, total = await get_queue_page(page)
    await _safe_edit(
        query,
        format_queue_page(items, page, total),
        reply_markup=queue_keyboard(items, page, total),
    )


async def _show_item(query, item_id: str):
    item = await db_manager.get_item(item_id)
    if item is None:
        await _safe_edit(query, "❌ Новость не найдена", reply_markup=_BACK_TO_QUEUE)
        return
    await _safe_edit(query, format_details(item), reply_markup=item_keyboard(item_id))


async def _approve(query, item_id: str):
    item = await db_manager.get_item(item_id)
    if item is None:
        await _safe_edit(query, "❌ Новость не найдена", reply_markup=_BACK_TO_QUEUE)
        return
    if await db_manager.approve(item_id):
        await _safe_edit(
            query,
            f"✅ Одобрено: {item.title[:80]}\n\n"
            "Будет опубликовано автоматически (с учётом лимита в час).",
            reply_markup=_BACK_TO_QUEUE,
        )
    else:
        await _safe_edit(
            query,
            "❌ Не удалось одобрить (возможно, статус уже изменился)",
            reply_markup=_BACK_TO_QUEUE,
        )


async def _reject(query, item_id: str):
    item = await db_manager.get_item(item_id)
    if item is None:
        await _safe_edit(query, "❌ Новость не найдена", reply_markup=_BACK_TO_QUEUE)
        return
    if await db_manager.reject(item_id, reason="rejected by admin"):
        await _safe_edit(query, f"❌ Отклонено: {item.title[:80]}", reply_markup=_BACK_TO_QUEUE)
    else:
        await _safe_edit(query, "❌ Не удалось отклонить", reply_markup=_BACK_TO_QUEUE)


async def _delete(query, item_id: str):
    item = await db_manager.get_item(item_id)
    if item is None:
        await _safe_edit(query, "❌ Новость не найдена", reply_markup=_BACK_TO_QUEUE)
        return
    if await db_manager.delete_item(item_id):
        await _safe_edit(
            query, f"🗑 Удалено из базы: {item.title[:80]}", reply_markup=_BACK_TO_QUEUE
        )
    else:
        await _safe_edit(query, "❌ Не удалось удалить", reply_markup=_BACK_TO_QUEUE)


async def _reject_all_confirm(query):
    count = await db_manager.count_by_status(NewsStatus.PROCESSED)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Да, отклонить все", callback_data="rejectall_yes"),
                InlineKeyboardButton("❌ Отмена", callback_data="rejectall_no"),
            ]
        ]
    )
    await _safe_edit(
        query,
        f"⚠️ Отклонить ВСЕ {count} новостей в очереди модерации?\n\n"
        "Они останутся в базе со статусом «отклонено».",
        reply_markup=keyboard,
    )


async def _reject_all(query):
    count = await db_manager.reject_all_pending()
    await _safe_edit(query, f"🗑 Отклонено {count} новостей.", reply_markup=_BACK_TO_QUEUE)


async def _show_status(query):
    stats = await db_manager.get_stats()
    pending = await db_manager.count_by_status(NewsStatus.PROCESSED)
    queued = await db_manager.count_by_status(NewsStatus.QUEUED)
    last_hour = await db_manager.published_in_last_hour()
    message = format_status(stats, pending, queued, last_hour, settings.max_posts_per_hour)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔄 Обновить", callback_data="status_refresh")]]
    )
    await _safe_edit(query, message, reply_markup=keyboard)
