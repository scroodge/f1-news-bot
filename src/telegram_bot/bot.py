"""
Telegram bot process: admin moderation UI + rate-limited publisher.

All queue state lives in PostgreSQL. Redis only delivers a "new items"
nudge so the bot can notify the admin without hammering the DB.
"""

import asyncio
import logging

from telegram import Bot, BotCommand, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from ..config import settings
from ..database import db_manager
from ..models import NewsStatus
from ..services.redis_service import redis_service
from .handlers.callbacks import button_callback
from .handlers.commands import (
    help_command,
    publish_command,
    published_command,
    queue_command,
    start_command,
    status_command,
    view_command,
)
from .publisher import Publisher

logger = logging.getLogger(__name__)

NOTIFY_INTERVAL_SECONDS = 60


class F1NewsBot:
    """Bot application: handlers + publisher loop + admin notifications"""

    def __init__(self):
        self.application: Application | None = None
        self.bot: Bot | None = None
        self.publisher: Publisher | None = None
        self._stop_event: asyncio.Event | None = None

    async def initialize(self) -> bool:
        """Build the application and register handlers"""
        try:
            self.application = Application.builder().token(settings.telegram_bot_token).build()
            self.bot = self.application.bot
            self.publisher = Publisher(self.bot)

            self.application.add_handler(CallbackQueryHandler(button_callback))
            self.application.add_handler(CommandHandler("start", start_command))
            self.application.add_handler(CommandHandler("help", help_command))
            self.application.add_handler(CommandHandler("status", status_command))
            self.application.add_handler(CommandHandler("queue", queue_command))
            self.application.add_handler(CommandHandler("view", view_command))
            self.application.add_handler(CommandHandler("publish", publish_command))
            self.application.add_handler(CommandHandler("published", published_command))

            # Remove any stale webhook so polling receives all update types
            await self.bot.delete_webhook(drop_pending_updates=True)
            await self.publisher.resolve_channel_id()
            await self._set_bot_commands()

            logger.info("Telegram bot initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            return False

    async def _set_bot_commands(self):
        commands = [
            BotCommand("start", "🚀 Начать работу с ботом"),
            BotCommand("queue", "📋 Очередь модерации"),
            BotCommand("status", "📊 Статус системы"),
            BotCommand("published", "📰 Опубликованные новости"),
            BotCommand("view", "👁 Детали новости (по номеру)"),
            BotCommand("publish", "📢 Одобрить новость (по номеру)"),
            BotCommand("help", "📚 Справка"),
        ]
        try:
            await self.bot.set_my_commands(commands)
        except Exception as e:
            logger.error(f"Failed to set bot commands: {e}")

    async def _notify_loop(self):
        """Tell the admin when new items arrive (via the Redis signal)"""
        if not settings.telegram_admin_id:
            return
        while not self._stop_event.is_set():
            try:
                new_count = await redis_service.consume_pending_signal()
                if new_count > 0:
                    pending = await db_manager.count_by_status(NewsStatus.PROCESSED)
                    await self.bot.send_message(
                        chat_id=settings.telegram_admin_id,
                        text=(
                            f"🆕 Новых новостей на модерации: {new_count}\n"
                            f"Всего в очереди: {pending}\n\n/queue"
                        ),
                    )
            except Exception as e:
                logger.error(f"Error in notify loop: {e}")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=NOTIFY_INTERVAL_SECONDS)
            except TimeoutError:
                pass

    async def run(self):
        """Run polling + publisher until stopped"""
        if not self.application:
            raise RuntimeError("Application is not initialized. Call initialize() first.")

        self._stop_event = asyncio.Event()

        publisher_task = asyncio.create_task(self.publisher.run(self._stop_event))
        notify_task = asyncio.create_task(self._notify_loop())

        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )

        try:
            await self._stop_event.wait()
        finally:
            try:
                await self.application.updater.stop()
            except Exception:
                pass
            await self.application.stop()
            await self.application.shutdown()
            await asyncio.gather(publisher_task, notify_task, return_exceptions=True)
            await redis_service.close()
            await db_manager.close()

    async def stop(self):
        if self._stop_event:
            self._stop_event.set()
