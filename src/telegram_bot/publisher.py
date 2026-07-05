"""
Publisher: takes approved (queued) items from PostgreSQL and posts them to
the channel, respecting the hourly rate limit. Rate limiting is computed from
the DB (published_to_channel_at timestamps) — no in-memory state.
"""

import asyncio
import logging

from telegram import Bot
from telegram.error import BadRequest

from ..config import settings
from ..database import db_manager
from ..models import ProcessedNewsItem, PublicationResult
from .formatting import format_channel_post

logger = logging.getLogger(__name__)


class Publisher:
    """Publishes queued news items to the Telegram channel"""

    def __init__(self, bot: Bot):
        self.bot = bot
        self.channel_id: int | str = settings.telegram_channel_id

    async def resolve_channel_id(self) -> None:
        """Resolve TELEGRAM_CHANNEL_ID (@username or numeric) to a chat id"""
        try:
            chat = await self.bot.get_chat(settings.telegram_channel_id)
            self.channel_id = chat.id
            logger.info(
                "Resolved channel '%s' -> chat_id=%s", settings.telegram_channel_id, chat.id
            )
        except Exception as e:
            logger.error("Failed to resolve channel id '%s': %s", settings.telegram_channel_id, e)
            # Keep the raw value; publish will surface a clear error

    async def publish(self, item: ProcessedNewsItem) -> PublicationResult:
        """Send one item to the channel and mark it published"""
        try:
            message = format_channel_post(item)
            sent = await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode=None,
                disable_web_page_preview=False,
            )
            await db_manager.mark_published(item.id, sent.message_id)
            logger.info(f"Published: {item.title[:50]}... (message_id={sent.message_id})")
            return PublicationResult(success=True, message_id=str(sent.message_id))
        except BadRequest as e:
            hint = ""
            if "chat not found" in str(e).lower():
                hint = (
                    " — Проверь TELEGRAM_CHANNEL_ID (используй @username ИЛИ числовой"
                    " -100XXXXXXXXXX) и права бота (добавь в канал и дай право публиковать)."
                )
            logger.error(f"Error publishing to channel: {e}")
            return PublicationResult(success=False, error_message=f"{e}{hint}")
        except Exception as e:
            logger.error(f"Error publishing to channel: {e}", exc_info=True)
            return PublicationResult(success=False, error_message=str(e))

    async def can_publish_now(self) -> bool:
        published = await db_manager.published_in_last_hour()
        return published < settings.max_posts_per_hour

    async def publish_next_if_allowed(self) -> PublicationResult | None:
        """One tick: publish the oldest queued item if under the rate limit"""
        if not await self.can_publish_now():
            return None
        item = await db_manager.next_queued_item()
        if item is None:
            return None
        return await self.publish(item)

    async def run(self, stop_event: asyncio.Event, interval_seconds: int = 60) -> None:
        """Publishing loop — runs inside the bot process"""
        logger.info("Publisher loop started")
        while not stop_event.is_set():
            try:
                result = await self.publish_next_if_allowed()
                if result is not None and not result.success:
                    logger.error(f"Publication failed: {result.error_message}")
            except Exception as e:
                logger.error(f"Error in publisher loop: {e}", exc_info=True)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except TimeoutError:
                pass
        logger.info("Publisher loop stopped")
