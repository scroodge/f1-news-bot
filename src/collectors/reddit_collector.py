"""
Reddit collector for F1 news
"""
import asyncio
from typing import List, Optional
from datetime import datetime, timedelta
import logging

import praw
from praw.models import Submission

from .base_collector import BaseCollector
from ..models import NewsItem, SourceType
from ..config import settings

logger = logging.getLogger(__name__)

class RedditCollector(BaseCollector):
    """Reddit collector for F1 news"""
    
    def __init__(self):
        super().__init__("Reddit", SourceType.REDDIT)
        self.reddit = None
        self.subreddits = ['formula1', 'F1Technical', 'motorsports']
    
    async def initialize(self):
        """Initialize Reddit client"""
        try:
            if not settings.reddit_client_id or not settings.reddit_client_secret:
                logger.warning("Reddit credentials not provided, skipping Reddit collection")
                return False
            
            self.reddit = praw.Reddit(
                client_id=settings.reddit_client_id,
                client_secret=settings.reddit_client_secret,
                user_agent=settings.reddit_user_agent
            )
            
            # Test connection
            self.reddit.user.me()
            logger.info("Reddit client initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Reddit client: {e}")
            return False
    
    async def collect_news(self) -> List[NewsItem]:
        """Collect news from Reddit"""
        if not self.reddit:
            if not await self.initialize():
                return []
        
        news_items = []
        
        try:
            for subreddit_name in self.subreddits:
                try:
                    subreddit_news = await self._collect_from_subreddit(subreddit_name)
                    news_items.extend(subreddit_news)
                except Exception as e:
                    logger.error(f"Error collecting from subreddit {subreddit_name}: {e}")
                    continue
            
            self.last_check = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Error in Reddit collection: {e}")
        
        return news_items
    
    async def _collect_from_subreddit(self, subreddit_name: str) -> List[NewsItem]:
        """Collect news from a specific subreddit"""
        news_items = []
        
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            
            # Get hot posts from last 24 hours
            for submission in subreddit.hot(limit=25):
                try:
                    # Skip if post is too old
                    post_date = datetime.fromtimestamp(submission.created_utc)
                    if post_date < datetime.utcnow() - timedelta(days=1):
                        continue
                    
                    news_item = self._parse_reddit_submission(submission, subreddit_name)
                    if news_item and news_item.relevance_score >= settings.min_relevance_score:
                        news_items.append(news_item)
                        
                except Exception as e:
                    logger.error(f"Error parsing Reddit submission: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error collecting from subreddit {subreddit_name}: {e}")
        
        return news_items
    
    def _parse_reddit_submission(self, submission: Submission, subreddit_name: str) -> Optional[NewsItem]:
        """Parse Reddit submission into NewsItem"""
        try:
            # Skip if not text post or too short
            if not submission.selftext and not submission.title:
                return None
            
            # Extract title
            title = submission.title.strip()
            if not title:
                return None
            
            # Extract content
            content = submission.selftext if submission.selftext else submission.title
            content = self.clean_content(content)
            
            # Create URL
            url = f"https://reddit.com{submission.permalink}"
            
            # Get published date
            published_at = datetime.fromtimestamp(submission.created_utc)
            
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
                source=f"Reddit: r/{subreddit_name}",
                source_type=self.source_type,
                published_at=published_at,
                relevance_score=relevance_score,
                keywords=keywords
            )
            
        except Exception as e:
            logger.error(f"Error parsing Reddit submission: {e}")
            return None
