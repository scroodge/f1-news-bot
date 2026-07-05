#!/usr/bin/env python3
"""
Standalone Telegram Bot for F1 News Moderation
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

Path("logs").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.FileHandler("logs/telegram_bot.log"), logging.StreamHandler()],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

REQUIRED_VARS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHANNEL_ID",
    "TELEGRAM_ADMIN_ID",
    "DATABASE_URL",
    "REDIS_URL",
]


def check_required_env_vars():
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v, "").strip()]
    if missing:
        print("❌ ОШИБКА: Отсутствуют обязательные переменные окружения:")
        for var in missing:
            print(f"   - {var}")
        print("\n📝 Создайте файл .env на основе .env.example и заполните переменные.")
        sys.exit(1)
    print("✅ Все обязательные переменные окружения настроены")


async def main():
    print("🤖 Starting F1 News Telegram Bot...")
    check_required_env_vars()

    from src.database import db_manager
    from src.telegram_bot.bot import F1NewsBot

    if not await db_manager.ping():
        print("❌ База данных недоступна — проверь DATABASE_URL (и SSH-туннель локально)")
        sys.exit(1)

    bot = F1NewsBot()
    if not await bot.initialize():
        print("❌ Failed to initialize Telegram bot")
        sys.exit(1)

    print("✅ Telegram bot started (polling). Press Ctrl+C to stop.")
    try:
        await bot.run()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✅ Telegram bot stopped")
