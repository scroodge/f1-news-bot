"""
Telegram Bot for publishing F1 news
"""

import asyncio
import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ..config import settings
from ..database import db_manager
from ..models import ProcessedNewsItem, PublicationResult, SourceType
from ..services.redis_service import redis_service
from ..utils.timezone import format_datetime

logger = logging.getLogger(__name__)


class F1NewsBot:
    """Telegram Bot for F1 news publication"""

    def __init__(self):
        self.bot: Bot | None = None
        self.application: Application | None = None
        self.channel_id = settings.telegram_channel_id
        self.pending_publications: list[ProcessedNewsItem] = []
        self.published_count: int = 0  # Счетчик опубликованных новостей
        self._stop_event: asyncio.Event | None = None
        self._editing_mode: dict = {}  # Словарь для отслеживания режима редактирования {user_id: {item_id, field}}

    async def initialize(self) -> bool:
        """
        Создаёт приложение, регистрирует хэндлеры и очищает возможный webhook.
        Запуск polling выполняется в self.run().
        """
        try:
            # Создаём приложение корректным способом (PTB v20+)
            self.application = Application.builder().token(settings.telegram_bot_token).build()
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

            # Добавляем обработчик текстовых сообщений для редактирования
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message)
            )

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
                BotCommand("publish", "📢 Опубликовать новость"),
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
            logger.error(
                "Failed to resolve channel id '%s': %s", str(settings.telegram_channel_id), e
            )
            # Keep whatever is in self.channel_id; publish will surface a clear error

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Проверяем, есть ли deep link для быстрой публикации или просмотра
        if context.args and context.args[0].startswith("publish_"):
            item_id = context.args[0].replace("publish_", "")
            await self._handle_quick_publish(item_id, update)
            return
        elif context.args and context.args[0].startswith("view_"):
            item_id = context.args[0].replace("view_", "")
            await self._handle_quick_view(item_id, update)
            return

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
                InlineKeyboardButton("📋 Очередь", callback_data="menu_queue"),
            ],
            [
                InlineKeyboardButton("👁️ Просмотр", callback_data="menu_view"),
                InlineKeyboardButton("📢 Публикация", callback_data="menu_publish"),
            ],
            [InlineKeyboardButton("📚 Справка", callback_data="menu_help")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(welcome_message, parse_mode=None, reply_markup=reply_markup)

    async def _handle_quick_publish(self, item_id: str, update: Update):
        """Обработка быстрой публикации через deep link"""
        try:
            # Находим новость по ID
            item = next((it for it in self.pending_publications if it.id == item_id), None)
            if not item:
                await update.message.reply_text("❌ Новость не найдена в очереди")
                return

            # Показываем предварительный просмотр
            message = "🚀 **Быстрая публикация:**\n\n"
            message += f"**Заголовок:** {item.title}\n\n"
            message += f"**Краткое содержание:**\n{item.summary}\n\n"
            message += f"**Источник:** {item.source}\n"
            message += f"**Важность:** {item.importance_level}/5\n\n"
            message += "Вы хотите опубликовать эту новость?"

            # Создаем кнопки для подтверждения
            keyboard = [
                [
                    InlineKeyboardButton("✅ Да, опубликовать", callback_data=f"publish_{item_id}"),
                    InlineKeyboardButton("❌ Отмена", callback_data="menu_start"),
                ],
                [
                    InlineKeyboardButton("📝 Редактировать", callback_data=f"edit_{item_id}"),
                    InlineKeyboardButton("👁️ Подробнее", callback_data=f"view_{item_id}"),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(message, parse_mode=None, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in quick publish: {e}", exc_info=True)
            await update.message.reply_text("❌ Ошибка быстрой публикации")

    async def _handle_quick_view(self, item_id: str, update: Update):
        """Обработка быстрого просмотра через deep link"""
        try:
            # Сначала ищем в очереди
            item = next((it for it in self.pending_publications if it.id == item_id), None)
            if item:
                # Новость в очереди
                message = "📰 **Детали новости (в очереди):**\n\n"
                message += f"**Заголовок:** {item.title}\n\n"
                message += f"**Краткое содержание:**\n{item.summary}\n\n"
                message += f"**Источник:** {item.source}\n"
                message += f"**Важность:** {item.importance_level}/5\n\n"
                message += "Эта новость находится в очереди на публикацию."

                keyboard = [
                    [
                        InlineKeyboardButton("✅ Опубликовать", callback_data=f"publish_{item.id}"),
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{item.id}"),
                    ],
                    [
                        InlineKeyboardButton("📝 Редактировать", callback_data=f"edit_{item.id}"),
                        InlineKeyboardButton("📋 К очереди", callback_data="queue_0"),
                    ],
                ]
            else:
                # Ищем в опубликованных
                try:
                    published_news = await db_manager.get_published_news(limit=1000, offset=0)
                    item = next((it for it in published_news if it.id == item_id), None)
                    if item:
                        message = "📰 **Детали опубликованной новости:**\n\n"
                        message += f"**Заголовок:** {item.title}\n\n"
                        message += f"**Краткое содержание:**\n{item.summary}\n\n"
                        message += f"**Источник:** {item.source}\n"
                        message += f"**Важность:** {item.importance_level}/5\n"
                        message += f"**Опубликовано:** {format_datetime(item.published_at)}\n\n"
                        message += "Эта новость уже была опубликована."

                        keyboard = [
                            [
                                InlineKeyboardButton(
                                    "📰 К опубликованным", callback_data="published_0"
                                )
                            ],
                            [InlineKeyboardButton("🏠 Главное меню", callback_data="menu_start")],
                        ]
                    else:
                        await update.message.reply_text("❌ Новость не найдена")
                        return
                except Exception as e:
                    logger.error(f"Failed to get published news: {e}")
                    await update.message.reply_text("❌ Новость не найдена")
                    return

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(message, parse_mode=None, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in quick view: {e}", exc_info=True)
            await update.message.reply_text("❌ Ошибка быстрого просмотра")

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
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu_start")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                status_message, parse_mode=None, reply_markup=reply_markup
            )
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
                    page = int(update.callback_query.data.split("_")[1])
                except (IndexError, ValueError):
                    page = 0

            items_per_page = 5
            start_idx = page * items_per_page
            end_idx = start_idx + items_per_page
            total_items = len(self.pending_publications)
            total_pages = (total_items + items_per_page - 1) // items_per_page

            queue_message = f"📋 Очередь публикаций (стр. {page + 1}/{total_pages}):\n\n"

            for i, item in enumerate(self.pending_publications[start_idx:end_idx], start_idx + 1):
                # Создаем ссылку для быстрой публикации
                publish_link = (
                    f"t.me/{self.bot.username}?start=publish_{item.id}"
                    if self.bot.username
                    else f"t.me/{self.bot.id}?start=publish_{item.id}"
                )

                # Форматируем время добавления в БД (в локальном часовом поясе)
                created_time = format_datetime(item.created_at) if item.created_at else "Неизвестно"

                queue_message += (
                    f"{i}. <a href='{publish_link}'>{item.title[:50]}...</a>\n"
                    f"   Источник: {item.source}\n"
                    f"   Релевантность: {item.relevance_score:.2f}\n"
                    f"   Важность: {item.importance_level}/5\n"
                    f"   📅 Добавлено: {created_time}\n\n"
                )

            # Создаем кнопки навигации
            keyboard = []
            if total_pages > 1:
                nav_buttons = []
                if page > 0:
                    nav_buttons.append(
                        InlineKeyboardButton("⬅️ Назад", callback_data=f"queue_{page - 1}")
                    )
                if page < total_pages - 1:
                    nav_buttons.append(
                        InlineKeyboardButton("Вперед ➡️", callback_data=f"queue_{page + 1}")
                    )
                if nav_buttons:
                    keyboard.append(nav_buttons)

                # Кнопки для быстрого перехода к страницам
                page_buttons = []
                for p in range(max(0, page - 2), min(total_pages, page + 3)):
                    if p == page:
                        page_buttons.append(
                            InlineKeyboardButton(f"•{p + 1}•", callback_data=f"queue_{p}")
                        )
                    else:
                        page_buttons.append(
                            InlineKeyboardButton(f"{p + 1}", callback_data=f"queue_{p}")
                        )
                if page_buttons:
                    keyboard.append(page_buttons)

            # Кнопки управления
            keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="queue_refresh")])
            keyboard.append(
                [InlineKeyboardButton("🗑️ Удалить новости", callback_data="queue_delete_menu")]
            )
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="menu_start")])

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

            if update.callback_query:
                await update.callback_query.edit_message_text(
                    queue_message, parse_mode="HTML", reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    queue_message, parse_mode="HTML", reply_markup=reply_markup
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
                    InlineKeyboardButton(
                        "✅ Опубликовать", callback_data=f"publish_{next_item.id}"
                    ),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{next_item.id}"),
                ],
                [InlineKeyboardButton("📝 Редактировать", callback_data=f"edit_{next_item.id}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            logger.info(
                "Created keyboard for item %s with buttons: publish_%s, reject_%s, edit_%s",
                next_item.id,
                next_item.id,
                next_item.id,
                next_item.id,
            )

            await update.message.reply_text(
                f"📰 Предварительный просмотр:\n\n{message}",
                parse_mode=None,
                reply_markup=reply_markup,
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

            # Используем переведенный заголовок, если доступен
            display_title = item.translated_title if item.translated_title else item.title
            message += f"**Заголовок:** {display_title}\n\n"

            # Используем переведенное содержание, если доступно
            if item.translated_summary:
                message += f"**Краткое содержание:**\n{item.translated_summary}\n\n"
            elif item.summary:
                message += f"**Краткое содержание:**\n{item.summary}\n\n"

            # Используем переведенные ключевые моменты, если доступны
            key_points_to_show = (
                item.translated_key_points if item.translated_key_points else item.key_points
            )
            if key_points_to_show:
                message += "**Ключевые моменты:**\n"
                for i, point in enumerate(key_points_to_show, 1):
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
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{item.id}"),
                ],
                [
                    InlineKeyboardButton("📝 Редактировать", callback_data=f"edit_{item.id}"),
                    InlineKeyboardButton("📋 К очереди", callback_data="queue_0"),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(message, parse_mode=None, reply_markup=reply_markup)

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
                    page = int(update.callback_query.data.split("_")[1])
                except (IndexError, ValueError):
                    page = 0

            items_per_page = 5
            offset = page * items_per_page

            # Получаем опубликованные новости из базы данных
            try:
                published_news = await db_manager.get_published_news(
                    limit=items_per_page, offset=offset
                )
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
                # Создаем ссылку для быстрого просмотра
                view_link = (
                    f"t.me/{self.bot.username}?start=view_{item.id}"
                    if self.bot.username
                    else f"t.me/{self.bot.id}?start=view_{item.id}"
                )

                # Форматируем время добавления в БД (в локальном часовом поясе)
                created_time = format_datetime(item.created_at) if item.created_at else "Неизвестно"

                message += f"{i}. <a href='{view_link}'>{item.title[:50]}...</a>\n"
                message += f"   Источник: {item.source}\n"
                message += f"   📅 Добавлено: {created_time}\n"
                message += f"   📢 Опубликовано: {format_datetime(item.published_at)}\n"
                message += f"   Важность: {item.importance_level}/5\n\n"

            # Создаем кнопки навигации
            keyboard = []
            if total_pages > 1:
                nav_buttons = []
                if page > 0:
                    nav_buttons.append(
                        InlineKeyboardButton("⬅️ Назад", callback_data=f"published_{page - 1}")
                    )
                if page < total_pages - 1:
                    nav_buttons.append(
                        InlineKeyboardButton("Вперед ➡️", callback_data=f"published_{page + 1}")
                    )
                if nav_buttons:
                    keyboard.append(nav_buttons)

                # Кнопки для быстрого перехода к страницам
                page_buttons = []
                for p in range(max(0, page - 2), min(total_pages, page + 3)):
                    if p == page:
                        page_buttons.append(
                            InlineKeyboardButton(f"•{p + 1}•", callback_data=f"published_{p}")
                        )
                    else:
                        page_buttons.append(
                            InlineKeyboardButton(f"{p + 1}", callback_data=f"published_{p}")
                        )
                if page_buttons:
                    keyboard.append(page_buttons)

            # Кнопки управления
            keyboard.append(
                [InlineKeyboardButton("🔄 Обновить", callback_data="published_refresh")]
            )
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="menu_start")])

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

            if update.callback_query:
                await update.callback_query.edit_message_text(
                    message, parse_mode="HTML", reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    message, parse_mode="HTML", reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"Error in published command: {e}")
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    "❌ Ошибка получения опубликованных новостей"
                )
            else:
                await update.message.reply_text("❌ Ошибка получения опубликованных новостей")

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений для редактирования новостей"""
        try:
            user_id = update.effective_user.id
            text = update.message.text

            # Проверяем, находится ли пользователь в режиме редактирования
            if user_id not in self._editing_mode:
                await update.message.reply_text(
                    "❓ Не понимаю, что вы хотите сделать.\n\n"
                    "Используйте команды из меню или кнопки для управления ботом.",
                    parse_mode=None,
                )
                return

            editing_info = self._editing_mode[user_id]
            item_id = editing_info.get("item_id")
            field = editing_info.get("field")

            if not item_id or not field:
                await update.message.reply_text("❌ Ошибка режима редактирования")
                return

            # Находим новость в очереди
            item = next((it for it in self.pending_publications if it.id == item_id), None)
            if not item:
                await update.message.reply_text("❌ Новость не найдена в очереди")
                # Выходим из режима редактирования
                if user_id in self._editing_mode:
                    del self._editing_mode[user_id]
                return

            # Обновляем поле новости
            if field == "title":
                old_title = item.title
                item.title = text
                message = "✅ **Заголовок обновлен!**\n\n"
                message += f"**Было:** {old_title}\n"
                message += f"**Стало:** {text}"

            elif field == "summary":
                old_summary = item.summary
                item.summary = text
                message = "✅ **Содержание обновлено!**\n\n"
                message += f"**Было:** {old_summary[:100]}...\n"
                message += f"**Стало:** {text[:100]}..."

            else:
                await update.message.reply_text("❌ Неизвестное поле для редактирования")
                return

            # Выходим из режима редактирования
            if user_id in self._editing_mode:
                del self._editing_mode[user_id]

            # Показываем результат и предлагаем дальнейшие действия
            keyboard = [
                [
                    InlineKeyboardButton("✅ Опубликовать", callback_data=f"publish_{item_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{item_id}"),
                ],
                [
                    InlineKeyboardButton("📝 Редактировать снова", callback_data=f"edit_{item_id}"),
                    InlineKeyboardButton("👁️ Подробнее", callback_data=f"view_{item_id}"),
                ],
                [InlineKeyboardButton("📋 К очереди", callback_data="queue_0")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(message, parse_mode=None, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error handling text message: {e}", exc_info=True)
            await update.message.reply_text("❌ Ошибка обработки сообщения")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Единая обработка callback_query с безопасным парсингом данных"""
        logger.info("=== BUTTON CALLBACK TRIGGERED ===")
        query = update.callback_query
        try:
            await query.answer()  # быстрое ACK, чтобы Telegram не показывал «подумайте»
            data = (query.data or "").strip()
            logger.info("Button callback received: %s", data)

            # Безопасный парсинг: action всегда есть, item_id может отсутствовать
            # Сначала проверяем специальные случаи
            if data == "queue_delete_menu":
                await self._handle_queue_delete_menu(query)
                return
            elif data.startswith("edit_field_"):
                parts = data.split("_", 2)  # edit, field, ITEM_ID_FIELD
                logger.info(f"Edit field parts: {parts}")
                if len(parts) >= 3:
                    item_id = parts[2].split("_")[0]  # Берем только ID (до следующего _)
                    field = parts[2].split("_")[1] if len(parts[2].split("_")) > 1 else None
                    logger.info(f"Parsed edit_field - item_id: {item_id}, field: {field}")
                    await self._handle_edit_field(item_id, field, query)
                else:
                    logger.error(f"Invalid edit_field format: {data}")
                    await query.edit_message_text("❌ Ошибка парсинга команды редактирования")
                return
            elif data.startswith("edit_set_"):
                parts = data.split("_", 2)  # edit, set, ITEM_ID_FIELD_VALUE
                if len(parts) >= 3:
                    remaining = parts[2].split("_")  # ITEM_ID_FIELD_VALUE
                    if len(remaining) >= 3:
                        item_id = remaining[0]
                        field = remaining[1]
                        value = remaining[2]
                        await self._handle_edit_set(item_id, field, value, query)
                    else:
                        await query.edit_message_text(
                            "❌ Ошибка парсинга команды установки значения"
                        )
                else:
                    await query.edit_message_text("❌ Ошибка парсинга команды установки значения")
                return
            elif data.startswith("edit_text_"):
                parts = data.split("_", 2)  # edit, text, ITEM_ID_FIELD
                if len(parts) >= 3:
                    remaining = parts[2].split("_")  # ITEM_ID_FIELD
                    if len(remaining) >= 2:
                        item_id = remaining[0]
                        field = remaining[1]
                        await self._handle_edit_text(item_id, field, query)
                    else:
                        await query.edit_message_text(
                            "❌ Ошибка парсинга команды редактирования текста"
                        )
                else:
                    await query.edit_message_text(
                        "❌ Ошибка парсинга команды редактирования текста"
                    )
                return
            elif data.startswith("copy_text_"):
                parts = data.split("_", 2)  # copy, text, ITEM_ID_FIELD
                if len(parts) >= 3:
                    remaining = parts[2].split("_")  # ITEM_ID_FIELD
                    if len(remaining) >= 2:
                        item_id = remaining[0]
                        field = remaining[1]
                        await self._handle_copy_text(item_id, field, query)
                    else:
                        await query.edit_message_text(
                            "❌ Ошибка парсинга команды копирования текста"
                        )
                else:
                    await query.edit_message_text("❌ Ошибка парсинга команды копирования текста")
                return

            # Обычный парсинг для остальных команд
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
            elif action == "view" and item_id:
                await self._handle_view(item_id, query)
            elif action == "edit_save" and item_id:
                await self._handle_edit_save(item_id, query)
            elif action == "edit_cancel" and item_id:
                await self._handle_edit_cancel(item_id, query)
            elif action == "queue":
                if item_id == "refresh":
                    # Обновляем очередь с проверкой изменений
                    await self._handle_queue_refresh(query)
                else:
                    # Переходим на страницу
                    await self.queue_command(update, context)
            elif action == "status":
                if item_id == "refresh":
                    # Обновляем статус
                    await self._handle_status_refresh(query)
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
                        parse_mode=None,
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
                            InlineKeyboardButton("📋 Очередь", callback_data="menu_queue"),
                        ],
                        [
                            InlineKeyboardButton("👁️ Просмотр", callback_data="menu_view"),
                            InlineKeyboardButton("📢 Публикация", callback_data="menu_publish"),
                        ],
                        [InlineKeyboardButton("📚 Справка", callback_data="menu_help")],
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    await query.edit_message_text(
                        welcome_message, parse_mode=None, reply_markup=reply_markup
                    )
            elif data.startswith("delete_item_"):
                item_id = data.replace("delete_item_", "")
                await self._handle_delete_item(item_id, query)
            elif data == "delete_all_confirm":
                await self._handle_delete_all_confirm(query)
            elif data == "delete_all_yes":
                await self._handle_delete_all_yes(query)
            elif data == "delete_all_no":
                await self._handle_delete_all_no(query)
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
                    if hasattr(result, "message_id"):
                        telegram_message_id = result.message_id

                    published_id = await db_manager.save_published_news(item, telegram_message_id)
                    logger.info(f"Published news saved to database with ID: {published_id}")
                except Exception as e:
                    logger.error(f"Failed to save published news to database: {e}")

                # удаляем опубликованный и увеличиваем счетчик
                self.pending_publications = [
                    it for it in self.pending_publications if it.id != item_id
                ]
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
            edit_message = "📝 **Редактирование новости:**\n\n"
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
                    InlineKeyboardButton(
                        "📝 Заголовок", callback_data=f"edit_field_{item_id}_title"
                    ),
                    InlineKeyboardButton(
                        "📄 Содержание", callback_data=f"edit_field_{item_id}_summary"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "⭐ Важность", callback_data=f"edit_field_{item_id}_importance"
                    ),
                    InlineKeyboardButton("🏷️ Теги", callback_data=f"edit_field_{item_id}_tags"),
                ],
                [
                    InlineKeyboardButton("✅ Сохранить", callback_data=f"edit_save_{item_id}"),
                    InlineKeyboardButton("❌ Отмена", callback_data=f"edit_cancel_{item_id}"),
                ],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu_start")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(edit_message, parse_mode=None, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error handling edit: {e}", exc_info=True)
            await query.edit_message_text("❌ Ошибка редактирования")

    async def _handle_edit_field(self, item_id: str, field: str, query):
        """Обработка выбора поля для редактирования"""
        try:
            logger.info(f"Looking for item with ID: {item_id}")
            logger.info(f"Available items: {[item.id for item in self.pending_publications]}")
            item = next((it for it in self.pending_publications if it.id == item_id), None)
            if not item:
                logger.error(f"Item not found with ID: {item_id}")
                await query.edit_message_text("❌ Новость не найдена")
                return

            if field == "title":
                message = "📝 **Редактирование заголовка:**\n\n"
                message += f"Текущий заголовок:\n{item.title}\n\n"
                message += "Выберите действие:"

                keyboard = [
                    [
                        InlineKeyboardButton(
                            "📝 Короткий заголовок", callback_data=f"edit_set_{item_id}_title_short"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📝 Длинный заголовок", callback_data=f"edit_set_{item_id}_title_long"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "✏️ Редактировать вручную", callback_data=f"edit_text_{item_id}_title"
                        )
                    ],
                    [InlineKeyboardButton("❌ Отмена", callback_data=f"edit_{item_id}")],
                ]

            elif field == "summary":
                message = "📄 **Редактирование содержания:**\n\n"
                message += f"Текущее содержание:\n{item.summary}\n\n"
                message += "Выберите действие:"

                keyboard = [
                    [
                        InlineKeyboardButton(
                            "📄 Краткое содержание",
                            callback_data=f"edit_set_{item_id}_summary_short",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📄 Подробное содержание",
                            callback_data=f"edit_set_{item_id}_summary_long",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "✏️ Редактировать вручную", callback_data=f"edit_text_{item_id}_summary"
                        )
                    ],
                    [InlineKeyboardButton("❌ Отмена", callback_data=f"edit_{item_id}")],
                ]

            elif field == "importance":
                message = "⭐ **Редактирование важности:**\n\n"
                message += f"Текущая важность: {item.importance_level}/5\n\n"
                message += "Выберите новую важность:"

                keyboard = [
                    [
                        InlineKeyboardButton(
                            "1 ⭐", callback_data=f"edit_set_{item_id}_importance_1"
                        ),
                        InlineKeyboardButton(
                            "2 ⭐", callback_data=f"edit_set_{item_id}_importance_2"
                        ),
                        InlineKeyboardButton(
                            "3 ⭐", callback_data=f"edit_set_{item_id}_importance_3"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "4 ⭐", callback_data=f"edit_set_{item_id}_importance_4"
                        ),
                        InlineKeyboardButton(
                            "5 ⭐", callback_data=f"edit_set_{item_id}_importance_5"
                        ),
                    ],
                    [InlineKeyboardButton("❌ Отмена", callback_data=f"edit_{item_id}")],
                ]

            elif field == "tags":
                message = "🏷️ **Редактирование тегов:**\n\n"
                message += f"Текущие теги: {', '.join(item.tags) if item.tags else 'Нет'}\n\n"
                message += "Выберите новые теги:"

                keyboard = [
                    [
                        InlineKeyboardButton("🏎️ F1", callback_data=f"edit_set_{item_id}_tags_f1"),
                        InlineKeyboardButton(
                            "🏆 Гонка", callback_data=f"edit_set_{item_id}_tags_race"
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            "🏁 Квалификация", callback_data=f"edit_set_{item_id}_tags_qualifying"
                        ),
                        InlineKeyboardButton(
                            "📊 Статистика", callback_data=f"edit_set_{item_id}_tags_stats"
                        ),
                    ],
                    [InlineKeyboardButton("❌ Отмена", callback_data=f"edit_{item_id}")],
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
                # Выходим из режима редактирования
                user_id = query.from_user.id
                if user_id in self._editing_mode:
                    del self._editing_mode[user_id]

                item = next((it for it in self.pending_publications if it.id == item_id), None)
                if not item:
                    await query.edit_message_text("❌ Новость не найдена")
                    return

                # Возвращаемся к просмотру новости
                message = "📰 **Детали новости:**\n\n"
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
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{item.id}"),
                    ],
                    [
                        InlineKeyboardButton("📝 Редактировать", callback_data=f"edit_{item.id}"),
                        InlineKeyboardButton("📋 К очереди", callback_data="queue_0"),
                    ],
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
                    item.summary = (
                        item.summary[:100] + "..." if len(item.summary) > 100 else item.summary
                    )
                elif value == "long":
                    item.summary = item.summary + "\n\nДополнительная информация будет добавлена."
                message = "✅ Содержание изменено"

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
                [
                    InlineKeyboardButton(
                        "📝 Продолжить редактирование", callback_data=f"edit_{item_id}"
                    )
                ],
                [InlineKeyboardButton("✅ Сохранить", callback_data=f"edit_save_{item_id}")],
                [InlineKeyboardButton("❌ Отмена", callback_data=f"edit_cancel_{item_id}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(message, parse_mode=None, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error handling edit set: {e}", exc_info=True)
            await query.edit_message_text("❌ Ошибка установки значения")

    async def _handle_edit_text(self, item_id: str, field: str, query):
        """Обработка ручного редактирования текста"""
        try:
            item = next((it for it in self.pending_publications if it.id == item_id), None)
            if not item:
                await query.edit_message_text("❌ Новость не найдена")
                return

            # Показываем текущий текст и инструкции
            if field == "title":
                current_text = item.title
                field_name = "заголовок"
            elif field == "summary":
                current_text = item.summary
                field_name = "содержание"
            else:
                await query.edit_message_text("❌ Неизвестное поле для редактирования")
                return

            # Устанавливаем режим редактирования для пользователя
            user_id = query.from_user.id
            self._editing_mode[user_id] = {"item_id": item_id, "field": field}

            message = f"✏️ **Редактирование {field_name}:**\n\n"
            message += f"Текущий {field_name}:\n{current_text}\n\n"
            message += "📝 **Отправьте новое значение в следующем сообщении!**\n\n"
            message += "Или используйте кнопки ниже:"

            keyboard = [
                [
                    InlineKeyboardButton(
                        "📋 Скопировать текущий текст", callback_data=f"copy_text_{item_id}_{field}"
                    )
                ],
                [InlineKeyboardButton("🔄 Обновить", callback_data=f"edit_text_{item_id}_{field}")],
                [InlineKeyboardButton("❌ Отмена", callback_data=f"edit_{item_id}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(message, parse_mode=None, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error handling edit text: {e}", exc_info=True)
            await query.edit_message_text("❌ Ошибка редактирования текста")

    async def _handle_copy_text(self, item_id: str, field: str, query):
        """Обработка копирования текста для редактирования"""
        try:
            item = next((it for it in self.pending_publications if it.id == item_id), None)
            if not item:
                await query.edit_message_text("❌ Новость не найдена")
                return

            # Получаем текст для копирования
            if field == "title":
                text_to_copy = item.title
                field_name = "заголовок"
            elif field == "summary":
                text_to_copy = item.summary
                field_name = "содержание"
            else:
                await query.edit_message_text("❌ Неизвестное поле для копирования")
                return

            message = f"📋 **Текст {field_name} для редактирования:**\n\n"
            message += f"```\n{text_to_copy}\n```\n\n"
            message += "Скопируйте текст выше, отредактируйте его и отправьте новое значение в следующем сообщении."

            keyboard = [
                [
                    InlineKeyboardButton(
                        "✏️ Редактировать снова", callback_data=f"edit_text_{item_id}_{field}"
                    )
                ],
                [InlineKeyboardButton("❌ Отмена", callback_data=f"edit_{item_id}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(message, parse_mode="Markdown", reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error handling copy text: {e}", exc_info=True)
            await query.edit_message_text("❌ Ошибка копирования текста")

    async def _handle_view(self, item_id: str, query):
        """Обработка просмотра деталей новости"""
        try:
            item = next((it for it in self.pending_publications if it.id == item_id), None)
            if not item:
                await query.edit_message_text("❌ Новость не найдена")
                return

            # Создаем детальное сообщение
            message = "📰 **Детали новости:**\n\n"
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
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{item.id}"),
                ],
                [
                    InlineKeyboardButton("📝 Редактировать", callback_data=f"edit_{item.id}"),
                    InlineKeyboardButton("📋 К очереди", callback_data="queue_0"),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(message, parse_mode=None, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error handling view: {e}", exc_info=True)
            await query.edit_message_text("❌ Ошибка просмотра новости")

    def _format_news_message(self, news_item: ProcessedNewsItem) -> str:
        message = f"🏎️ {news_item.title}\n\n"
        if news_item.summary:
            summary = (
                news_item.summary[:200] + "..."
                if len(news_item.summary) > 200
                else news_item.summary
            )
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
                disable_web_page_preview=False,
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
                        self.pending_publications.insert(0, news_item)  # Добавляем в начало списка
                        logger.info(
                            "Added news to moderation queue from Redis: %s...", news_item.title[:50]
                        )
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Error in Redis sync loop: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _handle_delete_item(self, item_id: str, query):
        """Удалить конкретную новость из очереди"""
        try:
            # Находим и удаляем новость
            item_to_remove = None
            for item in self.pending_publications:
                if item.id == item_id:
                    item_to_remove = item
                    break

            if item_to_remove:
                # Удаляем из локальной очереди
                self.pending_publications.remove(item_to_remove)

                # Удаляем из Redis
                try:
                    await redis_service.remove_news_from_moderation_queue(item_id)
                    logger.info(f"Removed news {item_id} from Redis moderation queue")
                except Exception as e:
                    logger.error(f"Error removing news from Redis: {e}")

                # Удаляем из базы данных
                try:
                    await db_manager.delete_news_item(item_id)
                    logger.info(f"Deleted news {item_id} from database")
                except Exception as e:
                    logger.error(f"Error deleting news from database: {e}")

                await query.edit_message_text(
                    f"✅ Новость удалена из очереди, Redis и базы данных:\n\n{item_to_remove.title[:100]}...",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("📋 К очереди", callback_data="queue_0")]]
                    ),
                )
            else:
                await query.edit_message_text("❌ Новость не найдена")

        except Exception as e:
            logger.error(f"Error deleting item: {e}")
            await query.edit_message_text("❌ Ошибка удаления новости")

    async def _handle_delete_all_confirm(self, query):
        """Показать подтверждение удаления всех новостей"""
        try:
            count = len(self.pending_publications)
            message = f"⚠️ ВНИМАНИЕ!\n\nВы собираетесь удалить ВСЕ {count} новостей из очереди.\n\nЭто действие нельзя отменить!\n\nПродолжить?"

            keyboard = [
                [
                    InlineKeyboardButton("✅ Да, удалить все", callback_data="delete_all_yes"),
                    InlineKeyboardButton("❌ Отмена", callback_data="delete_all_no"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(message, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in delete all confirm: {e}")
            await query.edit_message_text("❌ Ошибка подтверждения")

    async def _handle_delete_all_yes(self, query):
        """Удалить все новости из очереди"""
        try:
            count = len(self.pending_publications)
            item_ids = [item.id for item in self.pending_publications]

            # Очищаем локальную очередь
            self.pending_publications.clear()

            # Удаляем из Redis
            try:
                for item_id in item_ids:
                    await redis_service.remove_news_from_moderation_queue(item_id)
                logger.info(f"Removed {count} news items from Redis moderation queue")
            except Exception as e:
                logger.error(f"Error removing news from Redis: {e}")

            # Удаляем из базы данных
            try:
                for item_id in item_ids:
                    await db_manager.delete_news_item(item_id)
                logger.info(f"Deleted {count} news items from database")
            except Exception as e:
                logger.error(f"Error deleting news from database: {e}")

            await query.edit_message_text(
                f"✅ Удалено {count} новостей из очереди, Redis и базы данных",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("📋 К очереди", callback_data="queue_0")]]
                ),
            )

        except Exception as e:
            logger.error(f"Error deleting all items: {e}")
            await query.edit_message_text("❌ Ошибка удаления всех новостей")

    async def _handle_delete_all_no(self, query):
        """Отменить удаление всех новостей"""
        try:
            await query.edit_message_text(
                "❌ Удаление отменено",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("📋 К очереди", callback_data="queue_0")]]
                ),
            )
        except Exception as e:
            logger.error(f"Error cancelling delete all: {e}")
            await query.edit_message_text("❌ Ошибка отмены")

    async def _sync_with_redis(self):
        """Синхронизировать с Redis для получения новых новостей"""
        try:
            # Получаем только новые новости из Redis (те, которых нет в текущей очереди)
            redis_news = await redis_service.get_news_from_moderation_queue(limit=50)
            current_ids = {item.id for item in self.pending_publications}

            new_items = []
            for news_item in redis_news:
                if news_item.id not in current_ids:
                    new_items.append(news_item)
                    logger.info(
                        "Added news to moderation queue from Redis: %s...", news_item.title[:50]
                    )

            # Добавляем новые новости в начало списка
            if new_items:
                self.pending_publications = new_items + self.pending_publications

        except Exception as e:
            logger.error(f"Error syncing with Redis: {e}")

    async def _show_queue_page(self, query, page: int = 0):
        """Показать страницу очереди"""
        try:
            if not self.pending_publications:
                await query.edit_message_text("📭 Очередь публикаций пуста")
                return

            items_per_page = 4
            total_items = len(self.pending_publications)
            total_pages = (total_items + items_per_page - 1) // items_per_page
            page = max(0, min(page, total_pages - 1))

            start_idx = page * items_per_page
            end_idx = min(start_idx + items_per_page, total_items)
            page_items = self.pending_publications[start_idx:end_idx]

            queue_message = f"📋 **Очередь публикаций (стр. {page + 1}/{total_pages}):**\n\n"

            for i, item in enumerate(page_items, 1):
                item_num = start_idx + i
                title = item.title[:50] + "..." if len(item.title) > 50 else item.title
                source = (
                    f"Telegram: {item.source}"
                    if item.source_type == SourceType.TELEGRAM
                    else item.source
                )

                queue_message += f"{item_num}. **{title}**\n"
                queue_message += f"   Источник: {source}\n"
                queue_message += f"   Релевантность: {item.relevance_score:.2f}\n"
                queue_message += f"   Важность: {item.importance_level}/5\n\n"

            keyboard = []

            # Кнопки пагинации
            if total_pages > 1:
                page_buttons = []
                start_page = max(0, page - 2)
                end_page = min(total_pages, page + 3)

                for p in range(start_page, end_page):
                    if p == page:
                        page_buttons.append(
                            InlineKeyboardButton(f"•{p + 1}•", callback_data=f"queue_{p}")
                        )
                    else:
                        page_buttons.append(
                            InlineKeyboardButton(f"{p + 1}", callback_data=f"queue_{p}")
                        )
                if page_buttons:
                    keyboard.append(page_buttons)

            # Кнопки управления
            keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="queue_refresh")])
            keyboard.append(
                [InlineKeyboardButton("🗑️ Удалить новости", callback_data="queue_delete_menu")]
            )
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="menu_start")])

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

            await query.edit_message_text(
                queue_message, parse_mode="HTML", reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error in show queue page: {e}")
            await query.edit_message_text("❌ Ошибка получения очереди")

    async def _handle_status_refresh(self, query):
        """Обновить статус с проверкой изменений"""
        try:
            # Получаем статистику из базы данных
            published_stats = await db_manager.get_published_stats()
            queue_count = len(self.pending_publications)

            # Формируем сообщение статуса
            status_message = "📊 **Статус системы:**\n\n"
            status_message += "🟢 Сборщик новостей: 🟢 Активна\n"
            status_message += "🟢 AI обработка: 🟢 Активна\n"
            status_message += "🟢 Модерация: 🟢 Активна\n"
            status_message += "🟢 Публикация: 🟢 Активна\n\n"

            status_message += "📈 **Статистика:**\n"
            status_message += (
                f"• Новостей собрано: {published_stats.get('total_news', 0) + queue_count}\n"
            )
            status_message += (
                f"• Новостей обработано: {published_stats.get('total_news', 0) + queue_count}\n"
            )
            status_message += (
                f"• Новостей опубликовано: {published_stats.get('published_news', 0)}\n"
            )
            status_message += f"• В очереди: {queue_count}\n\n"

            status_message += "📅 **Публикации:**\n"
            status_message += f"• Сегодня: {published_stats.get('today_published', 0)}\n"
            status_message += f"• За неделю: {published_stats.get('this_week_published', 0)}\n\n"

            status_message += "⏰ Последнее обновление: Сейчас"

            # Кнопки
            keyboard = [
                [InlineKeyboardButton("🔄 Обновить", callback_data="status_refresh")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="menu_start")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                status_message, parse_mode=None, reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error in status refresh: {e}")
            await query.edit_message_text("❌ Ошибка обновления статуса")

    async def _handle_queue_refresh(self, query):
        """Обновить очередь с проверкой изменений"""
        try:
            # Получаем текущие ID новостей
            current_ids = {item.id for item in self.pending_publications}

            # Синхронизируем с Redis
            await self._sync_with_redis()

            # Проверяем, изменилось ли что-то
            new_ids = {item.id for item in self.pending_publications}

            if new_ids != current_ids:
                # Есть изменения - показываем обновленную очередь
                await self._show_queue_page(query, page=0)
            else:
                # Нет изменений - показываем сообщение об этом
                await query.edit_message_text(
                    "🔄 Очередь обновлена\n\nНовых новостей не найдено",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("📋 К очереди", callback_data="queue_0")]]
                    ),
                )

        except Exception as e:
            logger.error(f"Error in queue refresh: {e}")
            await query.edit_message_text("❌ Ошибка обновления очереди")

    async def _handle_queue_delete_menu(self, query):
        """Показать меню удаления новостей из очереди"""
        try:
            if not self.pending_publications:
                await query.edit_message_text("📭 Очередь пуста - нечего удалять")
                return

            # Показываем первые 10 новостей с кнопками удаления
            items_per_page = 10
            items_to_show = self.pending_publications[:items_per_page]

            message = "🗑️ Выберите новости для удаления:\n\n"

            keyboard = []
            for i, item in enumerate(items_to_show, 1):
                message += f"{i}. {item.title[:60]}...\n"
                keyboard.append(
                    [InlineKeyboardButton(f"🗑️ Удалить {i}", callback_data=f"delete_item_{item.id}")]
                )

            # Кнопки управления
            keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="queue_0")])
            keyboard.append(
                [InlineKeyboardButton("🗑️ Удалить все", callback_data="delete_all_confirm")]
            )

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error in queue delete menu: {e}")
            await query.edit_message_text("❌ Ошибка отображения меню удаления")

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
