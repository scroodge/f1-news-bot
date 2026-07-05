"""
Shared handler helpers.
"""

import functools
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update

from ...config import settings
from ...database import db_manager
from ...models import NewsStatus, ProcessedNewsItem

logger = logging.getLogger(__name__)

QUEUE_PAGE_SIZE = 5


def admin_only(handler):
    """Ignore updates from anyone who is not the configured admin"""

    @functools.wraps(handler)
    async def wrapper(update: Update, context, *args, **kwargs):
        admin_id = settings.telegram_admin_id
        user = update.effective_user
        if admin_id and (user is None or str(user.id) != str(admin_id)):
            logger.warning("Ignoring update from non-admin user %s", user.id if user else "?")
            return None
        return await handler(update, context, *args, **kwargs)

    return wrapper


async def get_queue_page(page: int) -> tuple[list[ProcessedNewsItem], int]:
    """Items awaiting moderation for one page + total count"""
    total = await db_manager.count_by_status(NewsStatus.PROCESSED)
    items = await db_manager.get_by_status(
        NewsStatus.PROCESSED, limit=QUEUE_PAGE_SIZE, offset=page * QUEUE_PAGE_SIZE
    )
    return items, total


def queue_keyboard(items: list[ProcessedNewsItem], page: int, total: int) -> InlineKeyboardMarkup:
    """Buttons for a queue page: one row per item + navigation"""
    keyboard: list[list[InlineKeyboardButton]] = []
    for i, item in enumerate(items, start=1):
        keyboard.append(
            [
                InlineKeyboardButton(f"👁 {i}", callback_data=f"view_{item.id}"),
                InlineKeyboardButton(f"✅ {i}", callback_data=f"approve_{item.id}"),
                InlineKeyboardButton(f"❌ {i}", callback_data=f"reject_{item.id}"),
            ]
        )

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"queue_{page - 1}"))
    if (page + 1) * QUEUE_PAGE_SIZE < total:
        nav.append(InlineKeyboardButton("Вперёд ➡️", callback_data=f"queue_{page + 1}"))
    if nav:
        keyboard.append(nav)

    keyboard.append(
        [
            InlineKeyboardButton("🔄 Обновить", callback_data=f"queue_{page}"),
            InlineKeyboardButton("🗑 Отклонить все", callback_data="rejectall_confirm"),
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def item_keyboard(item_id: str) -> InlineKeyboardMarkup:
    """Actions for a single item in the detail view"""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Опубликовать", callback_data=f"approve_{item_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{item_id}"),
            ],
            [
                InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{item_id}"),
                InlineKeyboardButton("📋 К очереди", callback_data="queue_0"),
            ],
        ]
    )
