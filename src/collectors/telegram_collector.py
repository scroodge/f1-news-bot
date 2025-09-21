"""
Telegram channel collector for F1 news
"""
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat, User

from .base_collector import BaseCollector
from ..models import NewsItem, SourceType
from ..config import settings

logger = logging.getLogger(__name__)

class TelegramCollector(BaseCollector):
    """Telegram channel collector"""
    
    def __init__(self):
        super().__init__("Telegram Channels", SourceType.TELEGRAM)
        self.client = None
        self.channels = []
        self.collected_messages = []
    
    async def initialize(self):
        """Initialize Telegram client"""
        try:
            self.client = TelegramClient(
                'f1_news_bot',
                settings.telegram_api_id,
                settings.telegram_api_hash
            )
            await self.client.start(phone=settings.telegram_phone)
            logger.info("Telegram client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram client: {e}")
            raise
    
    async def collect_news(self) -> List[NewsItem]:
        """Collect news from Telegram channels"""
        if not self.client:
            await self.initialize()
        
        news_items = []
        
        try:
            # Get list of channels to monitor
            channels = await self._get_monitored_channels()
            
            for channel in channels:
                try:
                    channel_news = await self._collect_from_channel(channel)
                    news_items.extend(channel_news)
                except Exception as e:
                    logger.error(f"Error collecting from channel {channel}: {e}")
                    continue
            
            self.last_check = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Error in Telegram collection: {e}")
        
        return news_items
    
    async def _get_monitored_channels(self) -> List[str]:
        """Get list of channels to monitor"""
        # Default F1 channels to monitor
        default_channels = [
            '@formula1',  # Official F1 channel
            '@f1_official',  # Alternative F1 channel
            '@motorsport',  # Motorsport.com
            '@autosport',  # Autosport
            '@f1news',  # F1 News
            '@formula1news',  # Formula 1 News
        ]
        
        # You can add more channels or load from config
        return default_channels
    
    async def _collect_from_channel(self, channel_username: str) -> List[NewsItem]:
        """Collect news from a specific Telegram channel"""
        news_items = []
        
        try:
            # Get channel entity
            channel = await self.client.get_entity(channel_username)
            
            # Get messages from last 24 hours
            since_date = datetime.utcnow() - timedelta(hours=24)
            
            async for message in self.client.iter_messages(
                channel,
                offset_date=since_date,
                limit=50
            ):
                try:
                    news_item = self._parse_telegram_message(message, channel_username)
                    if news_item and news_item.relevance_score >= settings.min_relevance_score:
                        news_items.append(news_item)
                except Exception as e:
                    logger.error(f"Error parsing Telegram message: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error collecting from channel {channel_username}: {e}")
        
        return news_items
    
    def _parse_telegram_message(self, message, channel_username: str) -> Optional[NewsItem]:
        """Parse Telegram message into NewsItem"""
        try:
            # Skip if message is too old or not text
            if not message.text or message.date < datetime.utcnow() - timedelta(days=1):
                return None
            
            # Extract title (first line or first 100 characters)
            text = message.text.strip()
            title = text.split('\n')[0][:100]
            
            # Extract content
            content = text
            
            # Create URL (if message has forward info, use original URL)
            url = f"https://t.me/{channel_username.replace('@', '')}/{message.id}"
            
            # Calculate relevance and extract keywords
            relevance_score = self.calculate_relevance_score(title, content)
            keywords = self.extract_keywords(title, content)
            
            # Skip if not relevant enough
            if relevance_score < settings.min_relevance_score:
                return None
            
            return NewsItem(
                title=title,
                content=content,
                url=url,
                source=f"Telegram: {channel_username}",
                source_type=self.source_type,
                published_at=message.date,
                relevance_score=relevance_score,
                keywords=keywords
            )
            
        except Exception as e:
            logger.error(f"Error parsing Telegram message: {e}")
            return None
    
    async def close(self):
        """Close Telegram client"""
        if self.client:
            await self.client.disconnect()
            logger.info("Telegram client closed")
