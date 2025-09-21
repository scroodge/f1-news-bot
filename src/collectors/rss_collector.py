"""
RSS feed collector for F1 news
"""
import asyncio
import aiohttp
import feedparser
from typing import List, Optional
from datetime import datetime
import logging

from .base_collector import BaseCollector
from ..models import NewsItem, SourceType
from ..config import settings

logger = logging.getLogger(__name__)

class RSSCollector(BaseCollector):
    """RSS feed collector"""
    
    def __init__(self):
        super().__init__("RSS Feeds", SourceType.RSS)
        self.feeds = settings.rss_feeds
    
    async def collect_news(self) -> List[NewsItem]:
        """Collect news from RSS feeds"""
        news_items = []
        
        async with aiohttp.ClientSession() as session:
            for feed_url in self.feeds:
                try:
                    feed_news = await self._collect_from_feed(session, feed_url)
                    news_items.extend(feed_news)
                except Exception as e:
                    logger.error(f"Error collecting from RSS feed {feed_url}: {e}")
                    continue
        
        self.last_check = datetime.utcnow()
        return news_items
    
    async def _collect_from_feed(self, session: aiohttp.ClientSession, feed_url: str) -> List[NewsItem]:
        """Collect news from a single RSS feed"""
        news_items = []
        
        try:
            async with session.get(feed_url, timeout=30) as response:
                if response.status == 200:
                    content = await response.text()
                    feed = feedparser.parse(content)
                    
                    for entry in feed.entries:
                        try:
                            news_item = self._parse_rss_entry(entry, feed_url)
                            if news_item and news_item.relevance_score >= settings.min_relevance_score:
                                news_items.append(news_item)
                        except Exception as e:
                            logger.error(f"Error parsing RSS entry: {e}")
                            continue
                else:
                    logger.warning(f"RSS feed returned status {response.status}: {feed_url}")
                    
        except asyncio.TimeoutError:
            logger.error(f"Timeout while fetching RSS feed: {feed_url}")
        except Exception as e:
            logger.error(f"Error fetching RSS feed {feed_url}: {e}")
        
        return news_items
    
    def _parse_rss_entry(self, entry, feed_url: str) -> Optional[NewsItem]:
        """Parse RSS entry into NewsItem"""
        try:
            # Extract title
            title = entry.get('title', '').strip()
            if not title:
                return None
            
            # Extract content
            content = ''
            if hasattr(entry, 'summary'):
                content = entry.summary
            elif hasattr(entry, 'description'):
                content = entry.description
            elif hasattr(entry, 'content'):
                if isinstance(entry.content, list) and entry.content:
                    content = entry.content[0].get('value', '')
                elif isinstance(entry.content, str):
                    content = entry.content
            
            content = self.clean_content(content)
            
            # Extract URL
            url = entry.get('link', '')
            if not url:
                return None
            
            # Extract published date
            published_at = datetime.utcnow()
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_at = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                published_at = datetime(*entry.updated_parsed[:6])
            
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
                source=self._get_source_name(feed_url),
                source_type=self.source_type,
                published_at=published_at,
                relevance_score=relevance_score,
                keywords=keywords
            )
            
        except Exception as e:
            logger.error(f"Error parsing RSS entry: {e}")
            return None
    
    def _get_source_name(self, feed_url: str) -> str:
        """Extract source name from feed URL"""
        if 'formula1.com' in feed_url:
            return 'Formula 1 Official'
        elif 'motorsport.com' in feed_url:
            return 'Motorsport.com'
        elif 'autosport.com' in feed_url:
            return 'Autosport'
        else:
            return 'RSS Feed'
