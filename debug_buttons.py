#!/usr/bin/env python3
"""
Debug script to check if Telegram bot buttons work
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from src.config import settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)
logger = logging.getLogger(__name__)

async def start_command(update, context):
    """Handle /start command"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Test Publish", callback_data="publish_test123"),
            InlineKeyboardButton("❌ Test Reject", callback_data="reject_test123")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🧪 Test buttons - click them to see if they work:",
        reply_markup=reply_markup
    )

async def button_callback(update, context):
    """Handle button callbacks"""
    logger.info("=== BUTTON CALLBACK TRIGGERED ===")
    
    query = update.callback_query
    await query.answer()
    
    logger.info(f"Button data: {query.data}")
    
    data = query.data
    action, item_id = data.split('_', 1)
    
    if action == "publish":
        await query.edit_message_text("✅ Test publish button works!")
    elif action == "reject":
        await query.edit_message_text("❌ Test reject button works!")
    else:
        await query.edit_message_text("❓ Unknown button")

async def main():
    """Main function"""
    # Create application
    application = Application.builder().token(settings.telegram_bot_token).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Start polling
    logger.info("Starting debug bot...")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
