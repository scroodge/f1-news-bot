"""
Publication scheduler for managing post timing and frequency
"""
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from ..models import ProcessedNewsItem, PublicationResult
from ..config import settings

logger = logging.getLogger(__name__)

class PublicationScheduler:
    """Scheduler for managing publication timing and frequency"""
    
    def __init__(self):
        self.max_posts_per_hour = settings.max_posts_per_hour
        self.post_history = []  # Track recent posts
        self.publication_queue = []
        self.is_publishing = False
    
    def can_publish_now(self) -> bool:
        """Check if we can publish now based on rate limits"""
        now = datetime.utcnow()
        
        # Remove old posts from history (older than 1 hour)
        self.post_history = [
            post_time for post_time in self.post_history
            if now - post_time < timedelta(hours=1)
        ]
        
        # Check if we're under the limit
        return len(self.post_history) < self.max_posts_per_hour
    
    def get_next_publication_time(self) -> Optional[datetime]:
        """Get the next available publication time"""
        if self.can_publish_now():
            return datetime.utcnow()
        
        # Calculate when we can publish next
        if self.post_history:
            oldest_post = min(self.post_history)
            next_time = oldest_post + timedelta(hours=1)
            return next_time
        
        return None
    
    def add_to_queue(self, news_item: ProcessedNewsItem, priority: int = 1) -> bool:
        """Add news item to publication queue"""
        try:
            queue_item = {
                'news_item': news_item,
                'priority': priority,
                'added_at': datetime.utcnow(),
                'scheduled_for': self._calculate_schedule_time(priority)
            }
            
            # Insert based on priority and schedule time
            inserted = False
            for i, item in enumerate(self.publication_queue):
                if (item['priority'] < priority or 
                    (item['priority'] == priority and item['scheduled_for'] > queue_item['scheduled_for'])):
                    self.publication_queue.insert(i, queue_item)
                    inserted = True
                    break
            
            if not inserted:
                self.publication_queue.append(queue_item)
            
            logger.info(f"Added news item to publication queue: {news_item.title[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Error adding to publication queue: {e}")
            return False
    
    def _calculate_schedule_time(self, priority: int) -> datetime:
        """Calculate when to schedule the post based on priority"""
        now = datetime.utcnow()
        
        if priority >= 5:  # High priority - immediate
            return now
        elif priority >= 3:  # Medium priority - within 30 minutes
            return now + timedelta(minutes=30)
        else:  # Low priority - within 2 hours
            return now + timedelta(hours=2)
    
    def get_ready_for_publication(self) -> List[ProcessedNewsItem]:
        """Get news items ready for publication"""
        ready_items = []
        now = datetime.utcnow()
        
        # Find items that are ready to publish
        for item in self.publication_queue[:]:
            if item['scheduled_for'] <= now and self.can_publish_now():
                ready_items.append(item['news_item'])
                self.publication_queue.remove(item)
        
        return ready_items
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get publication queue status"""
        now = datetime.utcnow()
        
        return {
            'queue_length': len(self.publication_queue),
            'can_publish_now': self.can_publish_now(),
            'next_publication_time': self.get_next_publication_time(),
            'posts_in_last_hour': len(self.post_history),
            'max_posts_per_hour': self.max_posts_per_hour,
            'queue_items': [
                {
                    'title': item['news_item'].title[:50],
                    'priority': item['priority'],
                    'scheduled_for': item['scheduled_for'],
                    'added_at': item['added_at']
                }
                for item in self.publication_queue[:5]  # Show first 5 items
            ]
        }
    
    def mark_as_published(self, news_item: ProcessedNewsItem) -> bool:
        """Mark news item as published"""
        try:
            self.post_history.append(datetime.utcnow())
            logger.info(f"Marked as published: {news_item.title[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Error marking as published: {e}")
            return False
    
    def clear_queue(self):
        """Clear the publication queue"""
        self.publication_queue.clear()
        logger.info("Publication queue cleared")
    
    def remove_from_queue(self, news_item_id: str) -> bool:
        """Remove specific news item from queue"""
        try:
            for i, item in enumerate(self.publication_queue):
                if item['news_item'].id == news_item_id:
                    self.publication_queue.pop(i)
                    logger.info(f"Removed from queue: {news_item_id}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Error removing from queue: {e}")
            return False
    
    def get_optimal_publication_times(self) -> List[datetime]:
        """Get optimal times for publication based on F1 audience"""
        now = datetime.utcnow()
        optimal_times = []
        
        # F1 audience is most active during:
        # - European morning (8-10 AM CET)
        # - European evening (6-8 PM CET)
        # - Weekend afternoons
        
        # Calculate next optimal times
        for days_ahead in range(7):  # Next 7 days
            target_date = now + timedelta(days=days_ahead)
            
            # Morning slot (8-10 AM CET)
            morning_time = target_date.replace(hour=8, minute=0, second=0, microsecond=0)
            if morning_time > now:
                optimal_times.append(morning_time)
            
            # Evening slot (6-8 PM CET)
            evening_time = target_date.replace(hour=18, minute=0, second=0, microsecond=0)
            if evening_time > now:
                optimal_times.append(evening_time)
        
        return optimal_times[:10]  # Return next 10 optimal times
