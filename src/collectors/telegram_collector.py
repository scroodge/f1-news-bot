"""
Telegram channel collector for F1 news
"""
import asyncio
from typing import List, Optional
from datetime import datetime, timedelta
import logging
import re

from telethon import TelegramClient
from telethon.tl.types import Message
from telethon.errors import SessionPasswordNeededError, FloodWaitError

from .base_collector import BaseCollector
from ..models import NewsItem, SourceType
from ..config import settings, F1_KEYWORDS
from ..utils.timezone import get_hours_ago_utc, utc_now

logger = logging.getLogger(__name__)

class TelegramCollector(BaseCollector):
    """Telegram channel collector using Telethon"""
    
    def __init__(self):
        super().__init__("Telegram Channels", SourceType.TELEGRAM)
        self.channels = settings.telegram_channels
        self.client: Optional[TelegramClient] = None
        self.session_name = "f1_news_bot"
        
        # Telegram API credentials
        self.api_id = settings.telegram_api_id
        self.api_hash = settings.telegram_api_hash
        self.phone = settings.telegram_phone
        
        # Check if credentials are available
        if not all([self.api_id, self.api_hash, self.phone]):
            logger.warning("Telegram API credentials not configured. Telegram collector will be disabled.")
            self.enabled = False
        else:
            self.enabled = True
    
    async def initialize(self):
        """Initialize Telegram client"""
        if not self.enabled:
            logger.info("Telegram collector disabled - no API credentials")
            return
        
        try:
            self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)
            await self.client.start(phone=self.phone)
            
            # Check if we're authorized
            if not await self.client.is_user_authorized():
                logger.error("Telegram client not authorized. Please check credentials.")
                self.enabled = False
                return
            
            logger.info("Telegram client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Telegram client: {e}")
            self.enabled = False
    
    async def collect_news(self) -> List[NewsItem]:
        """Collect news from Telegram channels"""
        if not self.enabled:
            logger.info("Telegram collector is disabled")
            self.last_check = datetime.utcnow()
            return []
        
        if not self.client:
            await self.initialize()
            if not self.enabled:
                return []
        
        all_news = []
        
        for channel in self.channels:
            try:
                news_items = await self._collect_from_channel(channel)
                all_news.extend(news_items)
                logger.info(f"Collected {len(news_items)} items from {channel}")
            except Exception as e:
                logger.error(f"Error collecting from {channel}: {e}")
        
        self.last_check = datetime.utcnow()
        return all_news
    
    async def _collect_from_channel(self, channel: str) -> List[NewsItem]:
        """Collect news from a single Telegram channel"""
        try:
            # Get channel entity
            entity = await self.client.get_entity(channel)
            
            # Get messages from the last 24 hours (using UTC)
            since_date = get_hours_ago_utc(24)
            
            news_items = []
            async for message in self.client.iter_messages(
                entity, 
                limit=50,  # Limit to 50 messages per channel
                offset_date=since_date
            ):
                try:
                    # Check if message is F1 related
                    if not self._is_f1_related(message):
                        continue
                    
                    # Create news item
                    news_item = self._create_news_item(message, channel)
                    if news_item:
                        news_items.append(news_item)
                        
                except Exception as e:
                    logger.error(f"Error processing message {message.id}: {e}")
                    continue
            
            return news_items
            
        except FloodWaitError as e:
            logger.warning(f"Rate limited for {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            return []
        except Exception as e:
            logger.error(f"Error collecting from channel {channel}: {e}")
            return []
    
    def _is_f1_related(self, message: Message) -> bool:
        """Check if Telegram message is F1 related"""
        if not message.text:
            return False
        
        text = message.text.lower()
        
        # Use the professional relevance scoring algorithm
        score = self.calculate_relevance_score(text, text)
        
        # Return True if score is above minimum threshold
        return score >= 0.1  # Very low threshold to catch all potential F1 content
    
    def _create_news_item(self, message: Message, channel: str) -> Optional[NewsItem]:
        """Create NewsItem from Telegram message"""
        try:
            # Extract text content
            text = message.text or ""
            
            # Clean up text (remove extra whitespace, etc.)
            text = re.sub(r'\s+', ' ', text).strip()
            
            if not text:
                return None
            
            # Create title (first line or first 100 characters)
            lines = text.split('\n')
            title = lines[0][:100] if lines[0] else "Telegram Message"
            
            # Create content (full text)
            content = text
            
            # Create URL (link to message)
            channel_username = channel.replace('@', '') if channel.startswith('@') else channel
            url = f"https://t.me/{channel_username}/{message.id}"
            
            # Extract media information
            image_url = None
            video_url = None
            media_type = None
            
            if message.photo:
                # Get the largest photo size (skip PhotoStrippedSize objects)
                photo_sizes = [s for s in message.photo.sizes if hasattr(s, 'w') and hasattr(s, 'h')]
                if photo_sizes:
                    largest_photo = max(photo_sizes, key=lambda s: s.w * s.h)
                image_url = f"https://t.me/{channel_username}/{message.id}"
                media_type = "photo"
            elif message.video:
                video_url = f"https://t.me/{channel_username}/{message.id}"
                media_type = "video"
            elif message.document:
                if message.document.mime_type and message.document.mime_type.startswith('image/'):
                    image_url = f"https://t.me/{channel_username}/{message.id}"
                    media_type = "photo"
                elif message.document.mime_type and message.document.mime_type.startswith('video/'):
                    video_url = f"https://t.me/{channel_username}/{message.id}"
                    media_type = "video"
            
            # Create news item
            news_item = NewsItem(
                title=title,
                content=content,
                url=url,
                source=f"Telegram: {channel}",
                source_type=SourceType.TELEGRAM,
                published_at=message.date.replace(tzinfo=None) if message.date else datetime.utcnow(),
                image_url=image_url,
                video_url=video_url,
                media_type=media_type
            )
            
            # Calculate relevance score and extract keywords
            news_item.relevance_score = self.calculate_relevance_score(title, content)
            news_item.keywords = self.extract_keywords(title, content)
            
            return news_item
            
        except Exception as e:
            logger.error(f"Error creating news item from message: {e}")
            return None
    
    async def close(self):
        """Close collector"""
        if self.client:
            await self.client.disconnect()
        logger.info("Telegram collector closed")