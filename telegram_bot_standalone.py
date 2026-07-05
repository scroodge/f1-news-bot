#!/usr/bin/env python3
"""
Standalone Telegram Bot for F1 News Moderation
"""

# Applied PTB v20 run_polling launcher — rev2
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Setup logging
# Ensure logs directory exists
Path("logs").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.FileHandler("logs/telegram_bot.log"), logging.StreamHandler()],
)
logging.getLogger("telegram.ext").setLevel(logging.DEBUG)
logging.getLogger("telegram").setLevel(logging.INFO)
logger = logging.getLogger(__name__)


def check_required_env_vars():
    """Check that all required environment variables are set"""
    required_vars = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHANNEL_ID",
        "TELEGRAM_ADMIN_ID",
        "DATABASE_URL",
        "REDIS_URL",
    ]

    missing_vars = []
    for var in required_vars:
        value = os.environ.get(var)
        if not value or value.strip() == "":
            missing_vars.append(var)

    if missing_vars:
        print("❌ ОШИБКА: Отсутствуют обязательные переменные окружения:")
        for var in missing_vars:
            print(f"   - {var}")
        print(
            "\n📝 Создайте файл .env на основе .env.example и заполните все обязательные переменные."
        )
        sys.exit(1)

    print("✅ Все обязательные переменные окружения настроены и валидны")


def main():
    """Main function"""
    print("🤖 Starting F1 News Telegram Bot...")
    logger.info("Starting F1 News Telegram Bot...")

    check_required_env_vars()

    # Import here to ensure environment is set up
    from src.database import db_manager
    from src.telegram_bot.bot import F1NewsBot

    logger.info("Imports successful")

    # Initialize database
    logger.info("Initializing database...")
    db_manager.create_tables()
    logger.info("Database initialized")

    # Create and initialize bot
    logger.info("Creating bot instance...")
    bot = F1NewsBot()

    try:
        # Initialize bot
        logger.info("Initializing bot...")
        success = asyncio.get_event_loop().run_until_complete(bot.initialize())
        if not success:
            logger.error("Failed to initialize Telegram bot")
            print("❌ Failed to initialize Telegram bot")
            return

        logger.info("Telegram bot initialized successfully")
        print("✅ Telegram bot started successfully! (polling)")
        print("🛑 Press Ctrl+C to stop the bot")

        # Start polling loop (handles commands and callback buttons)
        asyncio.get_event_loop().run_until_complete(bot.run())

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, stopping bot...")
        print("\n🛑 Stopping Telegram bot...")
        asyncio.get_event_loop().run_until_complete(bot.stop())
        logger.info("Telegram bot stopped")
        print("✅ Telegram bot stopped")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"❌ Error: {e}")


main()
