"""
Telegram Bot for publishing F1 news
"""
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden

from ..models import ProcessedNewsItem, PublicationResult
from ..config import settings
from ..services.redis_service import redis_service
from ..database import db_manager

logger = logging.getLogger(__name__)

class F1NewsBot:
    """Telegram Bot for F1 news publication"""

    def __init__(self):
        self.bot: Optional[Bot] = None
        self.application: Optional[Application] = None
        self.channel_id = settings.telegram_channel_id
        self.pending_publications: List[ProcessedNewsItem] = []
        self._stop_event: asyncio.Event | None = None

    async def initialize(self) -> bool:
        """
        Создаёт приложение, регистрирует хэндлеры и очищает возможный webhook.
        Запуск polling выполняется в self.run().
        """
        try:
            # Создаём приложение корректным способом (PTB v20+)
            self.application = (
                Application.builder()
                .token(settings.telegram_bot_token)
                .build()
            )
            self.bot = self.application.bot

            # Хэндлеры — CallbackQueryHandler ставим ПЕРВЫМ
            self.application.add_handler(CallbackQueryHandler(self.button_callback))
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("queue", self.queue_command))
            self.application.add_handler(CommandHandler("publish", self.publish_command))
            self.application.add_handler(CommandHandler("test", self.test_command))
            self.application.add_handler(CommandHandler("ping", self.ping_command))

            # Сносим старый webhook и дропаем висящие апдейты,
            # чтобы polling принимал ВСЕ типы, включая callback_query
            await self.bot.delete_webhook(drop_pending_updates=True)

            # Try to resolve channel id (support @username or numeric id)
            await self._resolve_channel_id()

            # Diagnostics command
            self.application.add_handler(CommandHandler("diag", self.diag_command))

            logger.info("Telegram bot initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            return False

    async def run(self):
        """
        Запуск polling с ручным циклом и корректным завершением.
        """
        if not self.application:
            raise RuntimeError("Application is not initialized. Call initialize() first.")

        # Фоновая синхронизация с Redis
        asyncio.create_task(self._redis_sync_loop())

        # Жизненный цикл PTB в асинхронном контексте
        await self.application.initialize()
        await self.application.start()

        # Safety: остановим возможный прежний poller
        try:
            await self.application.updater.stop()
        except Exception:
            pass

        # Стартуем polling
        await self.application.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )

        # Блокируемся до явной остановки
        self._stop_event = asyncio.Event()
        try:
            await self._stop_event.wait()
        finally:
            # Останавливаем updater и приложение
            try:
                await self.application.updater.stop()
            except Exception:
                pass
            await self.application.stop()
            await self.application.shutdown()

    async def _resolve_channel_id(self):
        """Resolve TELEGRAM_CHANNEL_ID to a numeric chat id and verify bot permissions."""
        try:
            raw = settings.telegram_channel_id
            # Prefer resolving via username or raw id
            chat = await self.bot.get_chat(raw)
            # For channels the id is negative and usually starts with -100
            self.channel_id = chat.id
            logger.info("Resolved channel '%s' -> chat_id=%s", str(raw), str(self.channel_id))
        except Exception as e:
            logger.error("Failed to resolve channel id '%s': %s", str(settings.telegram_channel_id), e)
            # Keep whatever is in self.channel_id; publish will surface a clear error

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_message = (
            "🏎️ F1 News Bot 🏎️\n\n"
            "Добро пожаловать в бота для автоматической публикации F1 новостей!\n\n"
            "Доступные команды:\n"
            "/help - Показать справку\n"
            "/status - Статус системы\n"
            "/queue - Показать очередь публикаций\n"
            "/publish - Опубликовать следующую новость\n\n"
            "Бот автоматически собирает новости из различных источников, "
            "обрабатывает их с помощью AI и публикует в ваш канал."
        )
        await update.message.reply_text(welcome_message, parse_mode=None)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_message = (
            "📚 Справка по командам:\n\n"
            "/start - Начать работу с ботом\n"
            "/help - Показать эту справку\n"
            "/status - Показать статус системы и статистику\n"
            "/queue - Показать очередь публикаций\n"
            "/publish - Опубликовать следующую новость из очереди\n\n"
            "Как работает бот:\n"
            "1) Собирает новости из RSS, Telegram каналов, Reddit\n"
            "2) Обрабатывает контент с помощью Ollama AI\n"
            "3) Модерирует и фильтрует контент\n"
            "4) Публикует в ваш канал\n"
        )
        await update.message.reply_text(help_message, parse_mode=None)

    async def diag_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show diagnostics: bot info, channel resolution, admin rights, queue size."""
        lines = []
        try:
            me = await self.bot.get_me()
            lines.append(f"🤖 Bot: @{me.username} (id: {me.id})")
        except Exception as e:
            lines.append(f"🤖 Bot: error getMe(): {e}")

        # Channel resolution
        raw = settings.telegram_channel_id
        lines.append(f"📡 Config TELEGRAM_CHANNEL_ID: {raw}")
        try:
            chat = await self.bot.get_chat(raw)
            lines.append(f"➡️ Resolved config to chat_id: {chat.id} | type: {chat.type}")
        except Exception as e:
            lines.append(f"❌ Failed to resolve config id: {e}")

        try:
            # Current effective target
            chat = await self.bot.get_chat(self.channel_id)
            lines.append(f"🎯 Effective target chat_id: {chat.id} | title: {getattr(chat, 'title', '')}")
            # Check admin rights
            try:
                admins = await self.bot.get_chat_administrators(chat.id)
                admin_ids = [a.user.id for a in admins]
                is_admin = (me.id in admin_ids)
                lines.append("🛡️ Bot admin in channel: " + ("YES" if is_admin else "NO"))
            except Forbidden:
                lines.append("🛡️ Bot admin in channel: NO (Forbidden to list admins)")
            except Exception as e:
                lines.append(f"🛡️ Admin check error: {e}")
        except Exception as e:
            lines.append(f"🎯 Effective target not reachable: {e}")

        # Queue size
        try:
            qsize = len(self.pending_publications)
            lines.append(f"🧾 Pending queue: {qsize}")
        except Exception:
            pass

        await update.message.reply_text("\n".join(lines), disable_web_page_preview=True)
        help_message = (
            "📚 Справка по командам:\n\n"
            "/start - Начать работу с ботом\n"
            "/help - Показать эту справку\n"
            "/status - Показать статус системы и статистику\n"
            "/queue - Показать очередь публикаций\n"
            "/publish - Опубликовать следующую новость из очереди\n\n"
            "Как работает бот:\n"
            "1) Собирает новости из RSS, Telegram каналов, Reddit\n"
            "2) Обрабатывает контент с помощью Ollama AI\n"
            "3) Модерирует и фильтрует контент\n"
            "4) Публикует в ваш канал\n"
        )
        await update.message.reply_text(help_message, parse_mode=None)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            status_message = (
                "📊 Статус системы:\n\n"
                "🟢 Сборщик новостей: Активен\n"
                "🟢 AI обработка: Активна\n"
                "🟢 Модерация: Активна\n"
                "🟢 Публикация: Активна\n\n"
                "📈 Статистика:\n"
                "• Новостей собрано: 0\n"
                "• Новостей обработано: 0\n"
                "• Новостей опубликовано: 0\n"
                "• В очереди: 0\n\n"
                "⏰ Последнее обновление: Сейчас"
            )
            await update.message.reply_text(status_message, parse_mode=None)
        except Exception as e:
            logger.error(f"Error in status command: {e}")
            await update.message.reply_text("❌ Ошибка получения статуса")

    async def queue_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self.pending_publications:
                await update.message.reply_text("📭 Очередь публикаций пуста")
                return

            queue_message = "📋 Очередь публикаций:\n\n"
            for i, item in enumerate(self.pending_publications[:5], 1):
                queue_message += (
                    f"{i}. {item.title[:50]}...\n"
                    f"   Источник: {item.source}\n"
                    f"   Релевантность: {item.relevance_score:.2f}\n"
                    f"   Важность: {item.importance_level}/5\n\n"
                )
            if len(self.pending_publications) > 5:
                queue_message += f"... и ещё {len(self.pending_publications) - 5} новостей"

            await update.message.reply_text(queue_message, parse_mode=None)
        except Exception as e:
            logger.error(f"Error in queue command: {e}")
            await update.message.reply_text("❌ Ошибка получения очереди")

    async def publish_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self.pending_publications:
                await update.message.reply_text("📭 Нет новостей для публикации")
                return

            next_item = self.pending_publications[0]
            message = self._format_news_message(next_item)

            keyboard = [
                [
                    InlineKeyboardButton("✅ Опубликовать", callback_data=f"publish_{next_item.id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{next_item.id}")
                ],
                [InlineKeyboardButton("📝 Редактировать", callback_data=f"edit_{next_item.id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            logger.info(
                "Created keyboard for item %s with buttons: publish_%s, reject_%s, edit_%s",
                next_item.id, next_item.id, next_item.id, next_item.id
            )

            await update.message.reply_text(
                f"📰 Предварительный просмотр:\n\n{message}",
                parse_mode=None,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error in publish command: {e}")
            await update.message.reply_text("❌ Ошибка публикации")

    async def test_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            keyboard = [[
                InlineKeyboardButton("✅ Test Publish", callback_data="publish_test123"),
                InlineKeyboardButton("❌ Test Reject", callback_data="reject_test123")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            logger.info("Created test keyboard with buttons: publish_test123, reject_test123")
            await update.message.reply_text("🧪 Test buttons - click them to see if they work:", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error in test command: {e}")
            await update.message.reply_text("❌ Ошибка теста")

    async def debug_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            keyboard = [[
                InlineKeyboardButton("🔍 Debug 1", callback_data="debug_1"),
                InlineKeyboardButton("🔍 Debug 2", callback_data="debug_2")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            logger.info("Created debug keyboard with buttons: debug_1, debug_2")
            await update.message.reply_text("🔍 Debug buttons - click them to see if they work:", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error in debug command: {e}")
            await update.message.reply_text("❌ Ошибка отладки")

    async def simple_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            keyboard = [[InlineKeyboardButton("OK", callback_data="ok")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            logger.info("Created simple keyboard with button: ok")
            await update.message.reply_text("Simple button test:", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error in simple command: {e}")
            await update.message.reply_text("❌ Ошибка простого теста")

    async def ping_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            keyboard = [[InlineKeyboardButton("Pong!", callback_data="pong")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            logger.info("Created ping keyboard with button: pong")
            await update.message.reply_text("Ping! Click the button:", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error in ping command: {e}")
            await update.message.reply_text("❌ Ошибка ping")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Единая обработка callback_query с безопасным парсингом данных"""
        logger.info("=== BUTTON CALLBACK TRIGGERED ===")
        query = update.callback_query
        try:
            await query.answer()  # быстрое ACK, чтобы Telegram не показывал «подумайте»
            data = (query.data or "").strip()
            logger.info("Button callback received: %s", data)

            # Безопасный парсинг: action всегда есть, item_id может отсутствовать
            parts = data.split("_", 1)
            action = parts[0]
            item_id = parts[1] if len(parts) == 2 else None
            logger.info("Parsed action='%s', item_id='%s'", action, item_id)

            if action == "publish" and item_id:
                if item_id == "test123":
                    await query.edit_message_text("✅ Test publish button works!")
                else:
                    await self._handle_publish(item_id, query)
            elif action == "reject" and item_id:
                if item_id == "test123":
                    await query.edit_message_text("❌ Test reject button works!")
                else:
                    await self._handle_reject(item_id, query)
            elif action == "edit" and item_id:
                await self._handle_edit(item_id, query)
            elif action == "debug":
                await query.edit_message_text(f"🔍 Debug button {item_id or ''} works!")
            elif action == "ok":
                await query.edit_message_text("✅ Simple button works!")
            elif action == "pong":
                await query.edit_message_text("🏓 Pong! Button works!")
            else:
                logger.warning("Unknown action or missing item_id: %s", data)
                await query.edit_message_text("❌ Неизвестная команда")
        except Exception as e:
            logger.error("Error handling button callback: %s", e, exc_info=True)
            try:
                await query.edit_message_text("❌ Ошибка обработки команды")
            except Exception:
                pass

    async def _handle_publish(self, item_id: str, query):
        try:
            item = next((it for it in self.pending_publications if it.id == item_id), None)
            if not item:
                await query.edit_message_text("❌ Новость не найдена")
                return
            result = await self.publish_to_channel(item)
            if result.success:
                # удаляем опубликованный
                self.pending_publications = [it for it in self.pending_publications if it.id != item_id]
                await query.edit_message_text("✅ Новость успешно опубликована!")
            else:
                await query.edit_message_text(f"❌ Ошибка публикации: {result.error_message}")
        except Exception as e:
            logger.error(f"Error handling publish: {e}", exc_info=True)
            await query.edit_message_text("❌ Ошибка публикации")

    async def _handle_reject(self, item_id: str, query):
        try:
            self.pending_publications = [it for it in self.pending_publications if it.id != item_id]
            await query.edit_message_text("❌ Новость отклонена")
        except Exception as e:
            logger.error(f"Error handling reject: {e}", exc_info=True)
            await query.edit_message_text("❌ Ошибка отклонения")

    async def _handle_edit(self, item_id: str, query):
        await query.edit_message_text("📝 Функция редактирования в разработке")

    def _format_news_message(self, news_item: ProcessedNewsItem) -> str:
        message = f"🏎️ {news_item.title}\n\n"
        if news_item.summary:
            summary = news_item.summary[:200] + "..." if len(news_item.summary) > 200 else news_item.summary
            message += f"📝 {summary}\n\n"
        if news_item.key_points:
            message += "🔑 Ключевые моменты:\n"
            for point in news_item.key_points[:2]:
                message += f"• {point}\n"
            message += "\n"
        message += f"📰 Источник: {news_item.source}\n"
        message += f"🔗 Читать: {news_item.url}"
        if news_item.tags:
            tags_str = " ".join([f"#{t.replace(' ', '_')}" for t in news_item.tags[:3]])
            message += f"\n\n{tags_str}"
        return message

    async def publish_to_channel(self, news_item: ProcessedNewsItem) -> PublicationResult:
        try:
            # Ensure channel id is numeric & resolved
            try:
                if isinstance(self.channel_id, str):
                    # Resolve again in case it changed
                    await self._resolve_channel_id()
            except Exception:
                pass
            message = self._format_news_message(news_item)
            sent = await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode=None,
                disable_web_page_preview=False
            )
            await db_manager.mark_as_published(news_item.id)
            await redis_service.mark_news_as_published(news_item.id, sent.message_id)
            return PublicationResult(success=True, message_id=str(sent.message_id))
        except BadRequest as e:
            # Typical cause: wrong channel id or bot is not admin in the channel
            hint = ""
            if "chat not found" in str(e).lower():
                hint = " — Проверь TELEGRAM_CHANNEL_ID (используй @username ИЛИ числовой -100XXXXXXXXXX) и права бота (добавь в канал и дай право публиковать)."
            logger.error(f"Error publishing to channel: {e}")
            return PublicationResult(success=False, error_message=f"{e}{hint}")
        except Exception as e:
            logger.error(f"Error publishing to channel: {e}", exc_info=True)
            return PublicationResult(success=False, error_message=str(e))

    async def add_to_pending(self, news_item: ProcessedNewsItem):
        self.pending_publications.append(news_item)
        logger.info("Added to pending publications: %s...", news_item.title[:50])

    async def _redis_sync_loop(self):
        while True:
            try:
                redis_news = await redis_service.get_news_from_moderation_queue(limit=5)
                for news_item in redis_news:
                    if not any(item.id == news_item.id for item in self.pending_publications):
                        self.pending_publications.append(news_item)
                        logger.info("Added news to moderation queue from Redis: %s...", news_item.title[:50])
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Error in Redis sync loop: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _send_next_item_for_moderation(self, context):
        if not self.pending_publications:
            return
        item = self.pending_publications[0]
        keyboard = [[
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{item.id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{item.id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        key_points_text = "\n".join([f"- {p}" for p in (item.key_points or [])]) or "Нет"
        tags_text = ", ".join(item.tags) if item.tags else "Нет"

        message_text = (
            f"Новая новость для модерации:\n\n"
            f"{item.title}\n\n"
            f"{item.summary or ''}\n\n"
            f"Ключевые моменты:\n{key_points_text}\n\n"
            f"Настроение: {item.sentiment}\n"
            f"Важность: {item.importance_level}/5\n"
            f"Теги: {tags_text}\n\n"
            f"Читать оригинал: {item.url}"
        )
        try:
            await self.bot.send_message(
                chat_id=settings.telegram_admin_id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode=None
            )
            logger.info("Sent news item %s for moderation to admin %s", item.id, settings.telegram_admin_id)
        except Exception as e:
            logger.error(f"Error sending news for moderation: {e}", exc_info=True)

    async def stop(self):
        """
        Если используешь run_polling — он сам корректно стопит приложение.
        Этот метод оставлен на случай явной остановки в другой модели запуска.
        """
        try:
            if self._stop_event and not self._stop_event.is_set():
                self._stop_event.set()
            if self.application:
                try:
                    await self.application.updater.stop()
                except Exception:
                    pass
                await self.application.stop()
                await self.application.shutdown()
        except Exception as e:
            logger.error(f"Error stopping bot: {e}", exc_info=True)
        logger.info("Telegram bot stopped")