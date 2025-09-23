"""
Redis service for inter-process communication
"""
import json
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import redis

from ..config import settings
from ..models import ProcessedNewsItem

logger = logging.getLogger(__name__)

class RedisService:
    """Redis service for communication between main app and Telegram bot"""
    
    def __init__(self):
        self.redis_client = redis.from_url(settings.redis_url)
        self.news_queue_key = "f1_news:moderation_queue"
        self.published_news_key = "f1_news:published"
        self.stats_key = "f1_news:stats"
    
    async def add_news_to_moderation_queue(self, news_item: ProcessedNewsItem) -> bool:
        """Add processed news item to moderation queue for Telegram bot"""
        try:
            # Convert ProcessedNewsItem to dict for Redis storage
            news_data = {
                "id": news_item.id,
                "title": news_item.title,
                "content": news_item.content,
                "url": news_item.url,
                "source": news_item.source,
                "source_type": news_item.source_type.value,
                "published_at": news_item.published_at.isoformat(),
                "relevance_score": news_item.relevance_score,
                "keywords": news_item.keywords,
                "processed": news_item.processed,
                "published": news_item.published,
                "created_at": news_item.created_at.isoformat(),
                "summary": news_item.summary,
                "key_points": news_item.key_points,
                "sentiment": news_item.sentiment,
                "importance_level": news_item.importance_level,
                "formatted_content": news_item.formatted_content,
                "tags": news_item.tags,
                "translated_title": news_item.translated_title,
                "translated_summary": news_item.translated_summary,
                "translated_key_points": news_item.translated_key_points,
                "original_language": news_item.original_language,
                "image_url": news_item.image_url,
                "video_url": news_item.video_url,
                "media_type": news_item.media_type,
                "added_to_queue_at": datetime.utcnow().isoformat()
            }
            
            # Add to Redis list (FIFO queue)
            self.redis_client.lpush(self.news_queue_key, json.dumps(news_data, default=str))
            
            # Set expiration for queue items (24 hours)
            self.redis_client.expire(self.news_queue_key, 86400)
            
            logger.info(f"Added news item to moderation queue: {news_item.title[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Error adding news to moderation queue: {e}")
            return False
    
    async def get_news_from_moderation_queue(self, limit: int = 10) -> List[ProcessedNewsItem]:
        """Get news items from moderation queue for Telegram bot"""
        try:
            # Get items from Redis list
            news_data_list = self.redis_client.lrange(self.news_queue_key, 0, limit - 1)
            
            news_items = []
            for news_data_json in news_data_list:
                try:
                    news_data = json.loads(news_data_json)
                    
                    # Convert back to ProcessedNewsItem
                    news_item = ProcessedNewsItem(
                        id=news_data["id"],
                        title=news_data["title"],
                        content=news_data["content"],
                        url=news_data["url"],
                        source=news_data["source"],
                        source_type=news_data["source_type"],
                        published_at=datetime.fromisoformat(news_data["published_at"]),
                        relevance_score=news_data["relevance_score"],
                        keywords=news_data["keywords"],
                        processed=news_data["processed"],
                        published=news_data["published"],
                        created_at=datetime.fromisoformat(news_data["created_at"]),
                        summary=news_data["summary"],
                        key_points=news_data["key_points"],
                        sentiment=news_data["sentiment"],
                        importance_level=news_data["importance_level"],
                        formatted_content=news_data["formatted_content"],
                        tags=news_data["tags"],
                        translated_title=news_data.get("translated_title"),
                        translated_summary=news_data.get("translated_summary"),
                        translated_key_points=news_data.get("translated_key_points", []),
                        original_language=news_data.get("original_language"),
                        image_url=news_data.get("image_url"),
                        video_url=news_data.get("video_url"),
                        media_type=news_data.get("media_type")
                    )
                    
                    news_items.append(news_item)
                    
                except Exception as e:
                    logger.error(f"Error parsing news item from Redis: {e}")
                    continue
            
            return news_items
            
        except Exception as e:
            logger.error(f"Error getting news from moderation queue: {e}")
            return []
    
    async def remove_news_from_moderation_queue(self, news_id: str) -> bool:
        """Remove specific news item from moderation queue"""
        try:
            # Get all items from queue
            news_data_list = self.redis_client.lrange(self.news_queue_key, 0, -1)
            
            # Find and remove the specific item
            for news_data_json in news_data_list:
                news_data = json.loads(news_data_json)
                if news_data["id"] == news_id:
                    # Remove this specific item
                    self.redis_client.lrem(self.news_queue_key, 1, news_data_json)
                    logger.info(f"Removed news item from moderation queue: {news_id}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error removing news from moderation queue: {e}")
            return False
    
    async def mark_news_as_published(self, news_id: str, message_id: int = None) -> bool:
        """Mark news item as published and remove from queue"""
        try:
            # Remove from moderation queue
            await self.remove_news_from_moderation_queue(news_id)
            
            # Add to published list for tracking
            published_data = {
                "news_id": news_id,
                "published_at": datetime.utcnow().isoformat(),
                "message_id": message_id
            }
            
            self.redis_client.lpush(self.published_news_key, json.dumps(published_data))
            self.redis_client.expire(self.published_news_key, 86400 * 7)  # Keep for 7 days
            
            logger.info(f"Marked news as published: {news_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error marking news as published: {e}")
            return False
    
    async def get_moderation_queue_length(self) -> int:
        """Get current length of moderation queue"""
        try:
            return self.redis_client.llen(self.news_queue_key)
        except Exception as e:
            logger.error(f"Error getting queue length: {e}")
            return 0
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get moderation queue status"""
        try:
            queue_length = await self.get_moderation_queue_length()
            
            return {
                "queue_length": queue_length,
                "queue_key": self.news_queue_key,
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return {"queue_length": 0, "error": str(e)}
    
    async def clear_moderation_queue(self) -> bool:
        """Clear all items from moderation queue"""
        try:
            self.redis_client.delete(self.news_queue_key)
            logger.info("Cleared moderation queue")
            return True
        except Exception as e:
            logger.error(f"Error clearing moderation queue: {e}")
            return False
    
    async def health_check(self) -> bool:
        """Check Redis connection health"""
        try:
            self.redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False

# Global Redis service instance
redis_service = RedisService()
