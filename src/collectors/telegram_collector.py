"""
Telegram channel collector for F1 news (Simplified version)
"""
import asyncio
from typing import List
from datetime import datetime
import logging

from .base_collector import BaseCollector
from ..models import NewsItem, SourceType
from ..config import settings, F1_KEYWORDS

logger = logging.getLogger(__name__)

class TelegramCollector(BaseCollector):
    """Telegram channel collector (simplified - requires telethon for full functionality)"""
    
    def __init__(self):
        super().__init__("Telegram Channels", SourceType.TELEGRAM)
        self.channels = settings.telegram_channels
    
    async def collect_news(self) -> List[NewsItem]:
        """Collect news from Telegram channels"""
        # This is a simplified version that returns empty list
        # Full implementation would require telethon library
        logger.info("Telegram collector is disabled (requires telethon library)")
        self.last_check = datetime.utcnow()
        return []
    
    async def close(self):
        """Close collector"""
        logger.info("Telegram collector closed")