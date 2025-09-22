#!/usr/bin/env python3
"""
Docker-optimized script to run both main application and Telegram bot
This version is designed to work properly in Docker containers
"""
import asyncio
import sys
import os
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.main import app
from src.telegram_bot.bot import F1NewsBot
import uvicorn
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_telegram_bot():
    """Run Telegram bot"""
    try:
        bot = F1NewsBot()
        await bot.initialize()
        if bot.application:
            await bot.run()
        else:
            logger.error("Failed to initialize Telegram bot")
    except Exception as e:
        logger.error(f"Error running Telegram bot: {e}")

async def run_main_app():
    """Run main FastAPI application"""
    try:
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8000,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()
    except Exception as e:
        logger.error(f"Error running main app: {e}")

async def main():
    """Main function - run both services concurrently"""
    logger.info("🚀 Starting F1 News Bot System in Docker...")
    logger.info("📱 Main app: http://0.0.0.0:8000")
    logger.info("🤖 Telegram bot: Starting...")
    
    try:
        # Run both services concurrently
        await asyncio.gather(
            run_main_app(),
            run_telegram_bot()
        )
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down...")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
