"""
RSS feed collector for F1 news
"""
import asyncio
import aiohttp
import feedparser
from typing import List
from datetime import datetime
import logging

from .base_collector import BaseCollector
from ..models import NewsItem, SourceType
from ..config import settings, F1_KEYWORDS

logger = logging.getLogger(__name__)

class RSSCollector(BaseCollector):
    """RSS feed collector"""
    
    def __init__(self):
        super().__init__("RSS Feeds", SourceType.RSS)
        self.feeds = settings.rss_feeds
        self.session = None
    
    async def initialize(self):
        """Initialize HTTP session"""
        self.session = aiohttp.ClientSession()
        logger.info("RSS collector initialized")
    
    async def collect_news(self) -> List[NewsItem]:
        """Collect news from RSS feeds"""
        if not self.session:
            await self.initialize()
        
        all_news = []
        
        for feed_url in self.feeds:
            try:
                news_items = await self._collect_from_feed(feed_url)
                all_news.extend(news_items)
                logger.info(f"Collected {len(news_items)} items from {feed_url}")
            except Exception as e:
                logger.error(f"Error collecting from {feed_url}: {e}")
        
        self.last_check = datetime.utcnow()
        return all_news
    
    async def _collect_from_feed(self, feed_url: str) -> List[NewsItem]:
        """Collect news from a single RSS feed"""
        try:
            async with self.session.get(feed_url, timeout=30) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch {feed_url}: {response.status}")
                    return []
                
                content = await response.text()
                feed = feedparser.parse(content)
                
                news_items = []
                for entry in feed.entries[:10]:  # Limit to 10 items per feed
                    try:
                        # Check if content is F1 related
                        if not self._is_f1_related(entry):
                            continue
                        
                        # Create news item
                        title = entry.get('title', '')
                        content = entry.get('summary', entry.get('description', ''))
                        
                        news_item = NewsItem(
                            title=title,
                            content=content,
                            url=entry.get('link', ''),
                            source=feed.feed.get('title', feed_url),
                            source_type=SourceType.RSS,
                            published_at=self._parse_date(entry.get('published', ''))
                        )
                        
                        # Calculate relevance score and extract keywords
                        news_item.relevance_score = self.calculate_relevance_score(title, content)
                        news_item.keywords = self.extract_keywords(title, content)
                        
                        news_items.append(news_item)
                        
                    except Exception as e:
                        logger.error(f"Error processing RSS entry: {e}")
                        continue
                
                return news_items
                
        except Exception as e:
            logger.error(f"Error collecting from RSS feed {feed_url}: {e}")
            return []
    
    def _is_f1_related(self, entry) -> bool:
        """Check if RSS entry is F1 related using professional scoring"""
        title = entry.get('title', '')
        content = entry.get('summary', entry.get('description', ''))
        
        # Use the professional relevance scoring algorithm
        score = self.calculate_relevance_score(title, content)
        
        # Return True if score is above minimum threshold
        return score >= 0.1  # Very low threshold to catch all potential F1 content
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime"""
        try:
            if not date_str:
                return datetime.utcnow()
            
            # Use dateutil parser for robust date parsing
            from dateutil import parser
            parsed_date = parser.parse(date_str)
            return parsed_date
            
        except Exception as e:
            logger.error(f"Error parsing date '{date_str}': {e}")
            return datetime.utcnow()
    
    async def close(self):
        """Close collector"""
        if self.session:
            await self.session.close()
        logger.info("RSS collector closed")