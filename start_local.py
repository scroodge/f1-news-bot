#!/usr/bin/env python3
"""
Local startup script for F1 News Bot
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))


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
        print("   Пример: cp .env.example .env")
        print("   Затем отредактируйте .env файл с вашими настройками.")
        sys.exit(1)

    # Check Telegram bot token format
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token or bot_token == "your_bot_token_here" or ":" not in bot_token:
        print("❌ ОШИБКА: Неверный формат TELEGRAM_BOT_TOKEN")
        print("   Токен должен быть в формате: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz")
        print("   Получите токен у @BotFather в Telegram")
        sys.exit(1)

    # Check channel ID format (@username or numeric -100XXXXXXXXXX)
    channel_id = os.environ.get("TELEGRAM_CHANNEL_ID", "")
    valid_channel = channel_id.startswith("@") or channel_id.lstrip("-").isdigit()
    if not channel_id or channel_id == "your_channel_id_here" or not valid_channel:
        print("❌ ОШИБКА: Неверный формат TELEGRAM_CHANNEL_ID")
        print("   Используйте @username канала или числовой ID (например: -1001234567890)")
        sys.exit(1)

    # Check admin ID format
    admin_id = os.environ.get("TELEGRAM_ADMIN_ID", "")
    if not admin_id or admin_id == "your_admin_id_here" or not admin_id.isdigit():
        print("❌ ОШИБКА: Неверный формат TELEGRAM_ADMIN_ID")
        print("   ID администратора должен быть числом (например: 123456789)")
        print("   Получите свой ID, написав боту @userinfobot")
        sys.exit(1)

    print("✅ Все обязательные переменные окружения настроены и валидны")


def setup_environment():
    """Setup environment variables for local development"""
    # Check required variables first
    check_required_env_vars()

    # Set default values for optional variables only if not set
    if not os.environ.get("LOG_LEVEL"):
        os.environ["LOG_LEVEL"] = "INFO"
    if not os.environ.get("DEBUG"):
        os.environ["DEBUG"] = "true"


def main():
    """Main function"""
    print("🚀 Starting F1 News Bot locally...")

    # Setup environment
    setup_environment()

    try:
        # Import and run the application
        import uvicorn

        print("✅ Application loaded successfully!")
        print("🌐 Starting FastAPI server on http://localhost:8000")
        print("📚 API documentation available at http://localhost:8000/docs")
        print("🛑 Press Ctrl+C to stop the server")

        # Run the server
        uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=False, log_level="info")

    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
