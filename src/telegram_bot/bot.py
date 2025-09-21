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

from ..models import ProcessedNewsItem, PublicationResult
from ..config import settings

logger = logging.getLogger(__name__)

class F1NewsBot:
    """Telegram Bot for F1 news publication"""
    
    def __init__(self):
        self.bot = Bot(token=settings.telegram_bot_token)
        self.application = None
        self.channel_id = settings.telegram_channel_id
        self.pending_publications = []
    
    async def initialize(self):
        """Initialize the bot"""
        try:
            self.application = Application.builder().token(settings.telegram_bot_token).build()
            
            # Add handlers
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("queue", self.queue_command))
            self.application.add_handler(CommandHandler("publish", self.publish_command))
            self.application.add_handler(CallbackQueryHandler(self.button_callback))
            
            logger.info("Telegram bot initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            return False
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_message = """
🏎️ **F1 News Bot** 🏎️

Добро пожаловать в бота для автоматической публикации F1 новостей!

**Доступные команды:**
/help - Показать справку
/status - Статус системы
/queue - Показать очередь публикаций
/publish - Опубликовать следующую новость

Бот автоматически собирает новости из различных источников, обрабатывает их с помощью AI и публикует в ваш канал.
        """
        
        await update.message.reply_text(welcome_message, parse_mode=ParseMode.MARKDOWN)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_message = """
📚 **Справка по командам:**

/start - Начать работу с ботом
/help - Показать эту справку
/status - Показать статус системы и статистику
/queue - Показать очередь публикаций
/publish - Опубликовать следующую новость из очереди

**Как работает бот:**
1. Собирает новости из RSS, Telegram каналов, Reddit
2. Обрабатывает контент с помощью Ollama AI
3. Модерирует и фильтрует контент
4. Публикует в ваш канал

**Источники новостей:**
• Formula 1 Official
• Motorsport.com
• Autosport
• Reddit r/formula1
• Telegram каналы
        """
        
        await update.message.reply_text(help_message, parse_mode=ParseMode.MARKDOWN)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        try:
            # Get system status (this would typically come from the main system)
            status_message = """
📊 **Статус системы:**

🟢 **Сборщик новостей:** Активен
🟢 **AI обработка:** Активна
🟢 **Модерация:** Активна
🟢 **Публикация:** Активна

📈 **Статистика:**
• Новостей собрано: 0
• Новостей обработано: 0
• Новостей опубликовано: 0
• В очереди: 0

⏰ **Последнее обновление:** Сейчас
            """
            
            await update.message.reply_text(status_message, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Error in status command: {e}")
            await update.message.reply_text("❌ Ошибка получения статуса")
    
    async def queue_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /queue command"""
        try:
            if not self.pending_publications:
                await update.message.reply_text("📭 Очередь публикаций пуста")
                return
            
            queue_message = "📋 **Очередь публикаций:**\n\n"
            
            for i, item in enumerate(self.pending_publications[:5], 1):
                queue_message += f"{i}. **{item.title[:50]}...**\n"
                queue_message += f"   Источник: {item.source}\n"
                queue_message += f"   Релевантность: {item.relevance_score:.2f}\n"
                queue_message += f"   Важность: {item.importance_level}/5\n\n"
            
            if len(self.pending_publications) > 5:
                queue_message += f"... и еще {len(self.pending_publications) - 5} новостей"
            
            await update.message.reply_text(queue_message, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Error in queue command: {e}")
            await update.message.reply_text("❌ Ошибка получения очереди")
    
    async def publish_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /publish command"""
        try:
            if not self.pending_publications:
                await update.message.reply_text("📭 Нет новостей для публикации")
                return
            
            # Get next item from queue
            next_item = self.pending_publications.pop(0)
            
            # Create publication message
            message = self._format_news_message(next_item)
            
            # Create inline keyboard for approval
            keyboard = [
                [
                    InlineKeyboardButton("✅ Опубликовать", callback_data=f"publish_{next_item.id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{next_item.id}")
                ],
                [
                    InlineKeyboardButton("📝 Редактировать", callback_data=f"edit_{next_item.id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"📰 **Предварительный просмотр:**\n\n{message}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error in publish command: {e}")
            await update.message.reply_text("❌ Ошибка публикации")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        action, item_id = data.split('_', 1)
        
        try:
            if action == "publish":
                await self._handle_publish(item_id, query)
            elif action == "reject":
                await self._handle_reject(item_id, query)
            elif action == "edit":
                await self._handle_edit(item_id, query)
                
        except Exception as e:
            logger.error(f"Error handling button callback: {e}")
            await query.edit_message_text("❌ Ошибка обработки команды")
    
    async def _handle_publish(self, item_id: str, query):
        """Handle publish action"""
        try:
            # Find the item in pending publications
            item = next((item for item in self.pending_publications if item.id == item_id), None)
            
            if not item:
                await query.edit_message_text("❌ Новость не найдена")
                return
            
            # Publish to channel
            result = await self.publish_to_channel(item)
            
            if result.success:
                await query.edit_message_text("✅ Новость успешно опубликована!")
            else:
                await query.edit_message_text(f"❌ Ошибка публикации: {result.error_message}")
                
        except Exception as e:
            logger.error(f"Error handling publish: {e}")
            await query.edit_message_text("❌ Ошибка публикации")
    
    async def _handle_reject(self, item_id: str, query):
        """Handle reject action"""
        try:
            # Remove from pending publications
            self.pending_publications = [item for item in self.pending_publications if item.id != item_id]
            await query.edit_message_text("❌ Новость отклонена")
            
        except Exception as e:
            logger.error(f"Error handling reject: {e}")
            await query.edit_message_text("❌ Ошибка отклонения")
    
    async def _handle_edit(self, item_id: str, query):
        """Handle edit action"""
        await query.edit_message_text("📝 Функция редактирования в разработке")
    
    def _format_news_message(self, news_item: ProcessedNewsItem) -> str:
        """Format news item for publication"""
        message = f"🏎️ **{news_item.title}**\n\n"
        
        if news_item.summary:
            message += f"📝 {news_item.summary}\n\n"
        
        if news_item.key_points:
            message += "🔑 **Ключевые моменты:**\n"
            for point in news_item.key_points[:3]:  # Show max 3 points
                message += f"• {point}\n"
            message += "\n"
        
        if news_item.formatted_content:
            message += f"{news_item.formatted_content}\n\n"
        
        message += f"📰 Источник: {news_item.source}\n"
        message += f"🔗 [Читать полностью]({news_item.url})"
        
        if news_item.tags:
            tags_str = " ".join([f"#{tag.replace(' ', '_')}" for tag in news_item.tags[:5]])
            message += f"\n\n{tags_str}"
        
        return message
    
    async def publish_to_channel(self, news_item: ProcessedNewsItem) -> PublicationResult:
        """Publish news item to channel"""
        try:
            message = self._format_news_message(news_item)
            
            # Send to channel
            sent_message = await self.bot.send_message(
                chat_id=self.channel_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=False
            )
            
            return PublicationResult(
                success=True,
                message_id=str(sent_message.message_id)
            )
            
        except Exception as e:
            logger.error(f"Error publishing to channel: {e}")
            return PublicationResult(
                success=False,
                error_message=str(e)
            )
    
    async def add_to_pending(self, news_item: ProcessedNewsItem):
        """Add news item to pending publications"""
        self.pending_publications.append(news_item)
        logger.info(f"Added to pending publications: {news_item.title[:50]}...")
    
    async def run(self):
        """Run the bot"""
        try:
            await self.application.run_polling()
        except Exception as e:
            logger.error(f"Error running bot: {e}")
    
    async def stop(self):
        """Stop the bot"""
        if self.application:
            await self.application.stop()
        logger.info("Telegram bot stopped")
