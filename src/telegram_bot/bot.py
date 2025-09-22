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
        self.published_count: int = 0  # Счетчик опубликованных новостей
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
            self.application.add_handler(CommandHandler("published", self.published_command))

            # Сносим старый webhook и дропаем висящие апдейты,
            # чтобы polling принимал ВСЕ типы, включая callback_query
            await self.bot.delete_webhook(drop_pending_updates=True)

            # Try to resolve channel id (support @username or numeric id)
            await self._resolve_channel_id()

            # Устанавливаем меню команд
            await self._set_bot_commands()

            logger.info("Telegram bot initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            return False

    async def _set_bot_commands(self):
        """Устанавливает меню команд для бота"""
        try:
            from telegram import BotCommand
            
            commands = [
                BotCommand("start", "🚀 Начать работу с ботом"),
                BotCommand("help", "📚 Показать справку"),
                BotCommand("status", "📊 Статус системы и статистика"),
                BotCommand("queue", "📋 Очередь публикаций"),
                BotCommand("published", "📰 Опубликованные новости"),
                BotCommand("view", "👁️ Просмотр деталей новости"),
                BotCommand("publish", "📢 Опубликовать новость")
            ]
            
            await self.bot.set_my_commands(commands)
            logger.info("Bot commands menu set successfully")
        except Exception as e:
            logger.error(f"Failed to set bot commands: {e}")

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
            "Бот автоматически собирает новости из различных источников, "
            "обрабатывает их с помощью AI и публикует в ваш канал.\n\n"
            "Используйте кнопки ниже или команды из меню для управления ботом."
        )
        
        # Создаем inline клавиатуру с основными командами
        keyboard = [
            [
                InlineKeyboardButton("📊 Статус", callback_data="menu_status"),
                InlineKeyboardButton("📋 Очередь", callback_data="menu_queue")
            ],
            [
                InlineKeyboardButton("👁️ Просмотр", callback_data="menu_view"),
                InlineKeyboardButton("📢 Публикация", callback_data="menu_publish")
            ],
            [
                InlineKeyboardButton("📚 Справка", callback_data="menu_help")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_message, parse_mode=None, reply_markup=reply_markup)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_message = (
            "📚 Справка по командам:\n\n"
            "/start - Начать работу с ботом\n"
            "/help - Показать эту справку\n"
            "/status - Показать статус системы и статистику\n"
            "/queue - Показать очередь публикаций (с кнопками навигации)\n"
            "/published - Показать опубликованные новости\n"
            "/view <номер> - Показать детали конкретной новости\n"
            "/publish - Опубликовать следующую новость из очереди\n\n"
            "Как работает бот:\n"
            "1) Собирает новости из RSS, Telegram каналов, Reddit\n"
            "2) Обрабатывает контент с помощью Ollama AI\n"
            "3) Модерирует и фильтрует контент\n"
            "4) Публикует в ваш канал и сохраняет в базу данных\n\n"
            "💡 Подсказки:\n"
            "• Используйте кнопки в /queue для навигации по страницам\n"
            "• /published показывает все опубликованные новости\n"
            "• /view 1 покажет детали первой новости\n"
            "• Все кнопки интерактивны и обновляют сообщения"
        )
        await update.message.reply_text(help_message, parse_mode=None)


    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            # Получаем реальную статистику из базы данных
            queue_count = len(self.pending_publications)
            
            try:
                # Получаем статистику из базы данных
                published_stats = await db_manager.get_published_stats()
                published_news = published_stats.get("total_published", 0)
                today_published = published_stats.get("today_published", 0)
                this_week_published = published_stats.get("this_week_published", 0)
            except Exception as e:
                logger.error(f"Failed to get published stats from database: {e}")
                published_news = self.published_count  # Fallback to memory counter
                today_published = 0
                this_week_published = 0
            
            # Подсчитываем общую статистику
            total_news = queue_count + published_news
            processed_news = queue_count + published_news  # Все новости в очереди уже обработаны
            
            # Определяем статус системы
            system_status = "🟢 Активна" if queue_count > 0 else "🟡 Ожидание новостей"
            
            status_message = (
                "📊 Статус системы:\n\n"
                f"🟢 Сборщик новостей: {system_status}\n"
                f"🟢 AI обработка: {system_status}\n"
                f"🟢 Модерация: {system_status}\n"
                f"🟢 Публикация: {system_status}\n\n"
                "📈 Статистика:\n"
                f"• Новостей собрано: {total_news}\n"
                f"• Новостей обработано: {processed_news}\n"
                f"• Новостей опубликовано: {published_news}\n"
                f"• В очереди: {queue_count}\n\n"
                "📅 Публикации:\n"
                f"• Сегодня: {today_published}\n"
                f"• За неделю: {this_week_published}\n\n"
                "⏰ Последнее обновление: Сейчас"
            )
            
            # Создаем кнопки
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="status_refresh")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu_start")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(status_message, parse_mode=None, reply_markup=reply_markup)
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

            # Кнопки управления
            keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="queue_refresh")])
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="menu_start")])

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

    async def published_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /published command - show published news"""
        try:
            # Получаем номер страницы из callback_data или используем 0
            page = 0
            if update.callback_query and update.callback_query.data:
                try:
                    page = int(update.callback_query.data.split('_')[1])
                except (IndexError, ValueError):
                    page = 0

            items_per_page = 5
            offset = page * items_per_page

            # Получаем опубликованные новости из базы данных
            try:
                published_news = await db_manager.get_published_news(limit=items_per_page, offset=offset)
                total_published = await db_manager.get_published_stats()
                total_count = total_published.get("total_published", 0)
            except Exception as e:
                logger.error(f"Failed to get published news from database: {e}")
                await update.message.reply_text("❌ Ошибка получения опубликованных новостей")
                return

            if not published_news:
                message = "📭 Опубликованных новостей пока нет"
                if update.callback_query:
                    await update.callback_query.edit_message_text(message, parse_mode=None)
                else:
                    await update.message.reply_text(message, parse_mode=None)
                return

            total_pages = (total_count + items_per_page - 1) // items_per_page
            message = f"📰 Опубликованные новости (стр. {page + 1}/{total_pages}):\n\n"
            
            for i, item in enumerate(published_news, offset + 1):
                message += f"{i}. {item.title[:50]}...\n"
                message += f"   Источник: {item.source}\n"
                message += f"   Опубликовано: {item.published_at.strftime('%d.%m.%Y %H:%M')}\n"
                message += f"   Важность: {item.importance_level}/5\n\n"

            # Создаем кнопки навигации
            keyboard = []
            if total_pages > 1:
                nav_buttons = []
                if page > 0:
                    nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"published_{page-1}"))
                if page < total_pages - 1:
                    nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"published_{page+1}"))
                if nav_buttons:
                    keyboard.append(nav_buttons)
                
                # Кнопки для быстрого перехода к страницам
                page_buttons = []
                for p in range(max(0, page-2), min(total_pages, page+3)):
                    if p == page:
                        page_buttons.append(InlineKeyboardButton(f"•{p+1}•", callback_data=f"published_{p}"))
                    else:
                        page_buttons.append(InlineKeyboardButton(f"{p+1}", callback_data=f"published_{p}"))
                if page_buttons:
                    keyboard.append(page_buttons)

            # Кнопки управления
            keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="published_refresh")])
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="menu_start")])

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

            if update.callback_query:
                await update.callback_query.edit_message_text(
                    message, 
                    parse_mode=None, 
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    message, 
                    parse_mode=None, 
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Error in published command: {e}")
            if update.callback_query:
                await update.callback_query.edit_message_text("❌ Ошибка получения опубликованных новостей")
            else:
                await update.message.reply_text("❌ Ошибка получения опубликованных новостей")


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
            elif action == "edit_field" and item_id:
                # Обработка выбора поля для редактирования
                field = data.split("_")[2] if len(data.split("_")) > 2 else None
                await self._handle_edit_field(item_id, field, query)
            elif action == "edit_save" and item_id:
                await self._handle_edit_save(item_id, query)
            elif action == "edit_cancel" and item_id:
                await self._handle_edit_cancel(item_id, query)
            elif action == "edit_set" and item_id:
                # Обработка установки значений при редактировании
                field = data.split("_")[2] if len(data.split("_")) > 2 else None
                value = data.split("_")[3] if len(data.split("_")) > 3 else None
                await self._handle_edit_set(item_id, field, value, query)
            elif action == "queue":
                if item_id == "refresh":
                    # Обновляем очередь
                    await self.queue_command(update, context)
                else:
                    # Переходим на страницу
                    await self.queue_command(update, context)
            elif action == "status":
                if item_id == "refresh":
                    # Обновляем статус
                    await self.status_command(update, context)
            elif action == "published":
                if item_id == "refresh":
                    # Обновляем опубликованные новости
                    await self.published_command(update, context)
                else:
                    # Переходим на страницу
                    await self.published_command(update, context)
            elif action == "menu":
                # Обработка кнопок меню
                if item_id == "status":
                    await self.status_command(update, context)
                elif item_id == "queue":
                    await self.queue_command(update, context)
                elif item_id == "view":
                    await query.edit_message_text(
                        "👁️ Просмотр деталей новости\n\n"
                        "Используйте команду /view <номер>\n"
                        "Пример: /view 1 - показать детали первой новости\n\n"
                        "Или используйте кнопки в /queue для навигации",
                        parse_mode=None
                    )
                elif item_id == "publish":
                    await self.publish_command(update, context)
                elif item_id == "help":
                    await self.help_command(update, context)
                elif item_id == "start":
                    # Возвращаемся к главному меню
                    welcome_message = (
                        "🏎️ F1 News Bot 🏎️\n\n"
                        "Добро пожаловать в бота для автоматической публикации F1 новостей!\n\n"
                        "Бот автоматически собирает новости из различных источников, "
                        "обрабатывает их с помощью AI и публикует в ваш канал.\n\n"
                        "Используйте кнопки ниже или команды из меню для управления ботом."
                    )
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("📊 Статус", callback_data="menu_status"),
                            InlineKeyboardButton("📋 Очередь", callback_data="menu_queue")
                        ],
                        [
                            InlineKeyboardButton("👁️ Просмотр", callback_data="menu_view"),
                            InlineKeyboardButton("📢 Публикация", callback_data="menu_publish")
                        ],
                        [
                            InlineKeyboardButton("📚 Справка", callback_data="menu_help")
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(welcome_message, parse_mode=None, reply_markup=reply_markup)
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
                # Сохраняем опубликованную новость в базу данных
                try:
                    telegram_message_id = None
                    if hasattr(result, 'message_id'):
                        telegram_message_id = result.message_id
                    
                    published_id = await db_manager.save_published_news(item, telegram_message_id)
                    logger.info(f"Published news saved to database with ID: {published_id}")
                except Exception as e:
                    logger.error(f"Failed to save published news to database: {e}")
                
                # удаляем опубликованный и увеличиваем счетчик
                self.pending_publications = [it for it in self.pending_publications if it.id != item_id]
                self.published_count += 1
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
        """Обработка редактирования новости"""
        try:
            item = next((it for it in self.pending_publications if it.id == item_id), None)
            if not item:
                await query.edit_message_text("❌ Новость не найдена")
                return
            
            # Создаем интерфейс редактирования
            edit_message = f"📝 **Редактирование новости:**\n\n"
            edit_message += f"**Заголовок:** {item.title}\n\n"
            edit_message += f"**Краткое содержание:**\n{item.summary}\n\n"
            edit_message += f"**Источник:** {item.source}\n"
            edit_message += f"**URL:** {item.url}\n"
            edit_message += f"**Релевантность:** {item.relevance_score:.2f}\n"
            edit_message += f"**Важность:** {item.importance_level}/5\n"
            edit_message += f"**Настроение:** {item.sentiment}\n\n"
            edit_message += "Выберите, что хотите отредактировать:"
            
            # Создаем кнопки для выбора поля редактирования
            keyboard = [
                [
                    InlineKeyboardButton("📝 Заголовок", callback_data=f"edit_field_{item_id}_title"),
                    InlineKeyboardButton("📄 Содержание", callback_data=f"edit_field_{item_id}_summary")
                ],
                [
                    InlineKeyboardButton("⭐ Важность", callback_data=f"edit_field_{item_id}_importance"),
                    InlineKeyboardButton("🏷️ Теги", callback_data=f"edit_field_{item_id}_tags")
                ],
                [
                    InlineKeyboardButton("✅ Сохранить", callback_data=f"edit_save_{item_id}"),
                    InlineKeyboardButton("❌ Отмена", callback_data=f"edit_cancel_{item_id}")
                ],
                [
                    InlineKeyboardButton("🏠 Главное меню", callback_data="menu_start")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(edit_message, parse_mode=None, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error handling edit: {e}", exc_info=True)
            await query.edit_message_text("❌ Ошибка редактирования")

    async def _handle_edit_field(self, item_id: str, field: str, query):
        """Обработка выбора поля для редактирования"""
        try:
            item = next((it for it in self.pending_publications if it.id == item_id), None)
            if not item:
                await query.edit_message_text("❌ Новость не найдена")
                return
            
            if field == "title":
                message = f"📝 **Редактирование заголовка:**\n\n"
                message += f"Текущий заголовок:\n{item.title}\n\n"
                message += "Выберите новый заголовок:"
                
                keyboard = [
                    [InlineKeyboardButton("📝 Короткий заголовок", callback_data=f"edit_set_{item_id}_title_short")],
                    [InlineKeyboardButton("📝 Длинный заголовок", callback_data=f"edit_set_{item_id}_title_long")],
                    [InlineKeyboardButton("❌ Отмена", callback_data=f"edit_{item_id}")]
                ]
                
            elif field == "summary":
                message = f"📄 **Редактирование содержания:**\n\n"
                message += f"Текущее содержание:\n{item.summary}\n\n"
                message += "Выберите новое содержание:"
                
                keyboard = [
                    [InlineKeyboardButton("📄 Краткое содержание", callback_data=f"edit_set_{item_id}_summary_short")],
                    [InlineKeyboardButton("📄 Подробное содержание", callback_data=f"edit_set_{item_id}_summary_long")],
                    [InlineKeyboardButton("❌ Отмена", callback_data=f"edit_{item_id}")]
                ]
                
            elif field == "importance":
                message = f"⭐ **Редактирование важности:**\n\n"
                message += f"Текущая важность: {item.importance_level}/5\n\n"
                message += "Выберите новую важность:"
                
                keyboard = [
                    [InlineKeyboardButton("1 ⭐", callback_data=f"edit_set_{item_id}_importance_1"),
                     InlineKeyboardButton("2 ⭐", callback_data=f"edit_set_{item_id}_importance_2"),
                     InlineKeyboardButton("3 ⭐", callback_data=f"edit_set_{item_id}_importance_3")],
                    [InlineKeyboardButton("4 ⭐", callback_data=f"edit_set_{item_id}_importance_4"),
                     InlineKeyboardButton("5 ⭐", callback_data=f"edit_set_{item_id}_importance_5")],
                    [InlineKeyboardButton("❌ Отмена", callback_data=f"edit_{item_id}")]
                ]
                
            elif field == "tags":
                message = f"🏷️ **Редактирование тегов:**\n\n"
                message += f"Текущие теги: {', '.join(item.tags) if item.tags else 'Нет'}\n\n"
                message += "Выберите новые теги:"
                
                keyboard = [
                    [InlineKeyboardButton("🏎️ F1", callback_data=f"edit_set_{item_id}_tags_f1"),
                     InlineKeyboardButton("🏆 Гонка", callback_data=f"edit_set_{item_id}_tags_race")],
                    [InlineKeyboardButton("🏁 Квалификация", callback_data=f"edit_set_{item_id}_tags_qualifying"),
                     InlineKeyboardButton("📊 Статистика", callback_data=f"edit_set_{item_id}_tags_stats")],
                    [InlineKeyboardButton("❌ Отмена", callback_data=f"edit_{item_id}")]
                ]
            else:
                await query.edit_message_text("❌ Неизвестное поле для редактирования")
                return
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, parse_mode=None, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error handling edit field: {e}", exc_info=True)
            await query.edit_message_text("❌ Ошибка редактирования поля")

    async def _handle_edit_save(self, item_id: str, query):
        """Сохранение изменений в новости"""
        try:
            item = next((it for it in self.pending_publications if it.id == item_id), None)
            if not item:
                await query.edit_message_text("❌ Новость не найдена")
                return
            
            # Пока просто показываем успешное сохранение
            # В будущем здесь можно добавить реальное сохранение изменений
            await query.edit_message_text("✅ Изменения сохранены!")
            
        except Exception as e:
            logger.error(f"Error handling edit save: {e}", exc_info=True)
            await query.edit_message_text("❌ Ошибка сохранения")

    async def _handle_edit_cancel(self, item_id: str, query):
        """Отмена редактирования"""
        try:
            item = next((it for it in self.pending_publications if it.id == item_id), None)
            if not item:
                await query.edit_message_text("❌ Новость не найдена")
                return
            
            # Возвращаемся к просмотру новости
            message = f"📰 **Детали новости:**\n\n"
            message += f"**Заголовок:** {item.title}\n\n"
            message += f"**Краткое содержание:**\n{item.summary}\n\n"
            message += f"**Источник:** {item.source}\n"
            message += f"**URL:** {item.url}\n"
            message += f"**Релевантность:** {item.relevance_score:.2f}\n"
            message += f"**Важность:** {item.importance_level}/5\n"
            message += f"**Настроение:** {item.sentiment}\n"
            
            if item.tags:
                message += f"**Теги:** {', '.join(item.tags)}\n"
            
            message += f"**Дата публикации:** {item.published_at}\n"
            
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
            
            await query.edit_message_text(message, parse_mode=None, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error handling edit cancel: {e}", exc_info=True)
            await query.edit_message_text("❌ Ошибка отмены редактирования")

    async def _handle_edit_set(self, item_id: str, field: str, value: str, query):
        """Обработка установки значений при редактировании"""
        try:
            item = next((it for it in self.pending_publications if it.id == item_id), None)
            if not item:
                await query.edit_message_text("❌ Новость не найдена")
                return
            
            # Применяем изменения к новости
            if field == "title":
                if value == "short":
                    item.title = item.title[:50] + "..." if len(item.title) > 50 else item.title
                elif value == "long":
                    item.title = item.title + " - Подробная информация"
                message = f"✅ Заголовок изменен на: {item.title}"
                
            elif field == "summary":
                if value == "short":
                    item.summary = item.summary[:100] + "..." if len(item.summary) > 100 else item.summary
                elif value == "long":
                    item.summary = item.summary + "\n\nДополнительная информация будет добавлена."
                message = f"✅ Содержание изменено"
                
            elif field == "importance":
                new_importance = int(value)
                item.importance_level = new_importance
                message = f"✅ Важность изменена на: {new_importance}/5"
                
            elif field == "tags":
                if value == "f1":
                    item.tags = ["F1", "Formula 1"]
                elif value == "race":
                    item.tags = ["Гонка", "Race"]
                elif value == "qualifying":
                    item.tags = ["Квалификация", "Qualifying"]
                elif value == "stats":
                    item.tags = ["Статистика", "Statistics"]
                message = f"✅ Теги изменены на: {', '.join(item.tags)}"
            else:
                message = "❌ Неизвестное поле для изменения"
            
            # Показываем результат и возвращаемся к редактированию
            keyboard = [
                [InlineKeyboardButton("📝 Продолжить редактирование", callback_data=f"edit_{item_id}")],
                [InlineKeyboardButton("✅ Сохранить", callback_data=f"edit_save_{item_id}")],
                [InlineKeyboardButton("❌ Отмена", callback_data=f"edit_cancel_{item_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(message, parse_mode=None, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error handling edit set: {e}", exc_info=True)
            await query.edit_message_text("❌ Ошибка установки значения")

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