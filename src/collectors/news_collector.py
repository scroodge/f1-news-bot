"""
Main news collector that orchestrates all data sources
"""
import asyncio
from typing import List, Dict, Any
from datetime import datetime
import logging

from .base_collector import BaseCollector
from .rss_collector import RSSCollector
from .telegram_collector import TelegramCollector
from .reddit_collector import RedditCollector
from ..models import NewsItem, SourceType
from ..database import db_manager

logger = logging.getLogger(__name__)

class NewsCollector:
    """Main news collector that manages all data sources"""
    
    def __init__(self):
        self.collectors: Dict[str, BaseCollector] = {}
        self._initialize_collectors()
    
    def _initialize_collectors(self):
        """Initialize all available collectors"""
        self.collectors = {
            'rss': RSSCollector(),
            'telegram': TelegramCollector(),
            'reddit': RedditCollector(),
        }
        logger.info(f"Initialized {len(self.collectors)} collectors")
    
    async def collect_all_news(self) -> List[NewsItem]:
        """Collect news from all sources"""
        all_news = []
        
        # Collect from each source concurrently
        tasks = []
        for name, collector in self.collectors.items():
            task = asyncio.create_task(self._collect_from_source(name, collector))
            tasks.append(task)
        
        # Wait for all collections to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(results):
            source_name = list(self.collectors.keys())[i]
            if isinstance(result, Exception):
                logger.error(f"Error collecting from {source_name}: {result}")
            else:
                all_news.extend(result)
                logger.info(f"Collected {len(result)} items from {source_name}")
        
        # Remove duplicates
        unique_news = self._remove_duplicates(all_news)
        logger.info(f"Total unique news items collected: {len(unique_news)}")
        
        return unique_news
    
    async def _collect_from_source(self, source_name: str, collector: BaseCollector) -> List[NewsItem]:
        """Collect news from a specific source"""
        try:
            news_items = await collector.collect_news()
            
            # Save to database
            saved_count = 0
            for item in news_items:
                try:
                    # Check for duplicates
                    if not await db_manager.check_duplicate(item.url):
                        await db_manager.save_news_item(item)
                        saved_count += 1
                except Exception as e:
                    logger.error(f"Error saving news item: {e}")
                    continue
            
            logger.info(f"Saved {saved_count} new items from {source_name}")
            return news_items
            
        except Exception as e:
            logger.error(f"Error collecting from {source_name}: {e}")
            return []
    
    def _remove_duplicates(self, news_items: List[NewsItem]) -> List[NewsItem]:
        """Remove duplicate news items"""
        unique_items = []
        seen_urls = set()
        seen_titles = set()
        
        for item in news_items:
            # Check URL uniqueness
            if item.url in seen_urls:
                continue
            
            # Check title similarity
            title_lower = item.title.lower()
            is_duplicate = False
            for seen_title in seen_titles:
                if self._calculate_similarity(title_lower, seen_title) > 0.8:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_items.append(item)
                seen_urls.add(item.url)
                seen_titles.add(title_lower)
        
        return unique_items
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity using simple word overlap"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    async def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics"""
        stats = {
            'total_collectors': len(self.collectors),
            'active_collectors': 0,
            'last_collection_time': None,
            'collection_errors': 0
        }
        
        for name, collector in self.collectors.items():
            if collector.last_check:
                stats['active_collectors'] += 1
                if not stats['last_collection_time'] or collector.last_check > stats['last_collection_time']:
                    stats['last_collection_time'] = collector.last_check
        
        return stats
    
    async def close(self):
        """Close all collectors"""
        for collector in self.collectors.values():
            if hasattr(collector, 'close'):
                await collector.close()
        logger.info("All collectors closed")
