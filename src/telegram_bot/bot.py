"""
Telegram Bot for publishing F1 news
"""
import asyncio
from typing import List, Optional
import logging

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

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
            self.application.add_handler(CommandHandler("view", self.view_command))

            # Сносим старый webhook и дропаем висящие апдейты,
            # чтобы polling принимал ВСЕ типы, включая callback_query
            await self.bot.delete_webhook(drop_pending_updates=True)

            # Try to resolve channel id (support @username or numeric id)
            await self._resolve_channel_id()

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
            "/queue - Показать очередь публикаций (с кнопками навигации)\n"
            "/view <номер> - Показать детали конкретной новости\n"
            "/publish - Опубликовать следующую новость из очереди\n\n"
            "Как работает бот:\n"
            "1) Собирает новости из RSS, Telegram каналов, Reddit\n"
            "2) Обрабатывает контент с помощью Ollama AI\n"
            "3) Модерирует и фильтрует контент\n"
            "4) Публикует в ваш канал\n\n"
            "💡 Подсказки:\n"
            "• Используйте кнопки в /queue для навигации по страницам\n"
            "• /view 1 покажет детали первой новости\n"
            "• Все кнопки интерактивны и обновляют сообщения"
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

            # Получаем номер страницы из callback_data или используем 0
            page = 0
            if update.callback_query and update.callback_query.data:
                try:
                    page = int(update.callback_query.data.split('_')[1])
                except (IndexError, ValueError):
                    page = 0

            items_per_page = 5
            start_idx = page * items_per_page
            end_idx = start_idx + items_per_page
            total_items = len(self.pending_publications)
            total_pages = (total_items + items_per_page - 1) // items_per_page

            queue_message = f"📋 Очередь публикаций (стр. {page + 1}/{total_pages}):\n\n"
            
            for i, item in enumerate(self.pending_publications[start_idx:end_idx], start_idx + 1):
                queue_message += (
                    f"{i}. {item.title[:50]}...\n"
                    f"   Источник: {item.source}\n"
                    f"   Релевантность: {item.relevance_score:.2f}\n"
                    f"   Важность: {item.importance_level}/5\n\n"
                )

            # Создаем кнопки навигации
            keyboard = []
            if total_pages > 1:
                nav_buttons = []
                if page > 0:
                    nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"queue_{page-1}"))
                if page < total_pages - 1:
                    nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"queue_{page+1}"))
                if nav_buttons:
                    keyboard.append(nav_buttons)
                
                # Кнопки для быстрого перехода к страницам
                page_buttons = []
                for p in range(max(0, page-2), min(total_pages, page+3)):
                    if p == page:
                        page_buttons.append(InlineKeyboardButton(f"•{p+1}•", callback_data=f"queue_{p}"))
                    else:
                        page_buttons.append(InlineKeyboardButton(f"{p+1}", callback_data=f"queue_{p}"))
                if page_buttons:
                    keyboard.append(page_buttons)

            # Кнопка обновления
            keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="queue_refresh")])

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

            if update.callback_query:
                await update.callback_query.edit_message_text(
                    queue_message, 
                    parse_mode=None, 
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    queue_message, 
                    parse_mode=None, 
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Error in queue command: {e}")
            if update.callback_query:
                await update.callback_query.edit_message_text("❌ Ошибка получения очереди")
            else:
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

    async def view_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /view command - show detailed info about specific news item"""
        try:
            if not context.args:
                await update.message.reply_text(
                    "📖 Использование: /view <номер>\n"
                    "Пример: /view 1 - показать детали первой новости"
                )
                return

            try:
                item_number = int(context.args[0])
            except ValueError:
                await update.message.reply_text("❌ Номер должен быть числом")
                return

            if not self.pending_publications:
                await update.message.reply_text("📭 Очередь публикаций пуста")
                return

            if item_number < 1 or item_number > len(self.pending_publications):
                await update.message.reply_text(
                    f"❌ Номер должен быть от 1 до {len(self.pending_publications)}"
                )
                return

            item = self.pending_publications[item_number - 1]
            
            # Создаем детальное сообщение
            message = f"📰 **Детали новости #{item_number}:**\n\n"
            message += f"**Заголовок:** {item.title}\n\n"
            
            if item.summary:
                message += f"**Краткое содержание:**\n{item.summary}\n\n"
            
            if item.key_points:
                message += "**Ключевые моменты:**\n"
                for i, point in enumerate(item.key_points, 1):
                    message += f"{i}. {point}\n"
                message += "\n"
            
            message += f"**Источник:** {item.source}\n"
            message += f"**URL:** {item.url}\n"
            message += f"**Релевантность:** {item.relevance_score:.2f}\n"
            message += f"**Важность:** {item.importance_level}/5\n"
            message += f"**Настроение:** {item.sentiment}\n"
            
            if item.tags:
                message += f"**Теги:** {', '.join(item.tags)}\n"
            
            message += f"**Дата публикации:** {item.published_at}\n"
            
            # Создаем кнопки для действий
            keyboard = [
                [
                    InlineKeyboardButton("✅ Опубликовать", callback_data=f"publish_{item.id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{item.id}")
                ],
                [
                    InlineKeyboardButton("📝 Редактировать", callback_data=f"edit_{item.id}"),
                    InlineKeyboardButton("📋 К очереди", callback_data="queue_0")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                message, 
                parse_mode=None, 
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error in view command: {e}")
            await update.message.reply_text("❌ Ошибка просмотра новости")


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
                await self._handle_publish(item_id, query)
            elif action == "reject" and item_id:
                await self._handle_reject(item_id, query)
            elif action == "edit" and item_id:
                await self._handle_edit(item_id, query)
            elif action == "queue":
                if item_id == "refresh":
                    # Обновляем очередь
                    await self.queue_command(update, context)
                else:
                    # Переходим на страницу
                    await self.queue_command(update, context)
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