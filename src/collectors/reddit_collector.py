"""
Reddit collector for F1 news (Simplified version)
"""

import logging
from datetime import datetime

from ..models import NewsItem, SourceType
from .base_collector import BaseCollector

logger = logging.getLogger(__name__)


class RedditCollector(BaseCollector):
    """Reddit collector (simplified - requires praw for full functionality)"""

    def __init__(self):
        super().__init__("Reddit", SourceType.REDDIT)
        self.subreddits = ["formula1", "F1Technical", "formula1memes"]

    async def collect_news(self) -> list[NewsItem]:
        """Collect news from Reddit"""
        # This is a simplified version that returns empty list
        # Full implementation would require praw library
        logger.info("Reddit collector is disabled (requires praw library)")
        self.last_check = datetime.utcnow()
        return []

    async def close(self):
        """Close collector"""
        logger.info("Reddit collector closed")
