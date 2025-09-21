"""
Database operations for F1 News Bot
"""
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, String, DateTime, Float, Boolean, Text, Integer, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import UUID
import uuid
import redis
import json

from .config import settings
from .models import NewsItem, ProcessedNewsItem, BotStats, SourceType

# Database setup
engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Redis setup
redis_client = redis.from_url(settings.redis_url)

class NewsItemDB(Base):
    """News item database model"""
    __tablename__ = "news_items"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    url = Column(String, nullable=False, unique=True)
    source = Column(String, nullable=False)
    source_type = Column(String, nullable=False)
    published_at = Column(DateTime, nullable=False)
    relevance_score = Column(Float, default=0.0)
    keywords = Column(JSON, default=list)
    processed = Column(Boolean, default=False)
    published = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Processed fields
    summary = Column(Text, nullable=True)
    key_points = Column(JSON, default=list)
    sentiment = Column(String, default="neutral")
    importance_level = Column(Integer, default=1)
    formatted_content = Column(Text, nullable=True)
    tags = Column(JSON, default=list)

class DatabaseManager:
    """Database operations manager"""
    
    def __init__(self):
        self.engine = engine
        self.redis = redis_client
    
    def create_tables(self):
        """Create all database tables"""
        Base.metadata.create_all(bind=self.engine)
    
    def get_session(self) -> Session:
        """Get database session"""
        return SessionLocal()
    
    async def save_news_item(self, news_item: NewsItem) -> str:
        """Save news item to database"""
        with self.get_session() as session:
            db_item = NewsItemDB(
                title=news_item.title,
                content=news_item.content,
                url=news_item.url,
                source=news_item.source,
                source_type=news_item.source_type.value,
                published_at=news_item.published_at,
                relevance_score=news_item.relevance_score,
                keywords=news_item.keywords,
                processed=news_item.processed,
                published=news_item.published
            )
            session.add(db_item)
            session.commit()
            return str(db_item.id)
    
    async def update_processed_news(self, news_id: str, processed_item: ProcessedNewsItem) -> bool:
        """Update news item with processed data"""
        with self.get_session() as session:
            db_item = session.query(NewsItemDB).filter(NewsItemDB.id == news_id).first()
            if not db_item:
                return False
            
            db_item.summary = processed_item.summary
            db_item.key_points = processed_item.key_points
            db_item.sentiment = processed_item.sentiment
            db_item.importance_level = processed_item.importance_level
            db_item.formatted_content = processed_item.formatted_content
            db_item.tags = processed_item.tags
            db_item.processed = True
            
            session.commit()
            return True
    
    async def mark_as_published(self, news_id: str) -> bool:
        """Mark news item as published"""
        with self.get_session() as session:
            db_item = session.query(NewsItemDB).filter(NewsItemDB.id == news_id).first()
            if not db_item:
                return False
            
            db_item.published = True
            session.commit()
            return True
    
    async def get_unprocessed_news(self, limit: int = 10) -> List[NewsItem]:
        """Get unprocessed news items"""
        with self.get_session() as session:
            db_items = session.query(NewsItemDB).filter(
                NewsItemDB.processed == False,
                NewsItemDB.relevance_score >= settings.min_relevance_score
            ).limit(limit).all()
            
            return [
                NewsItem(
                    id=str(item.id),
                    title=item.title,
                    content=item.content,
                    url=item.url,
                    source=item.source,
                    source_type=SourceType(item.source_type),
                    published_at=item.published_at,
                    relevance_score=item.relevance_score,
                    keywords=item.keywords or [],
                    processed=item.processed,
                    published=item.published,
                    created_at=item.created_at
                )
                for item in db_items
            ]
    
    async def get_news_for_publication(self, limit: int = 5) -> List[ProcessedNewsItem]:
        """Get processed news items ready for publication"""
        with self.get_session() as session:
            db_items = session.query(NewsItemDB).filter(
                NewsItemDB.processed == True,
                NewsItemDB.published == False
            ).order_by(NewsItemDB.importance_level.desc(), NewsItemDB.relevance_score.desc()).limit(limit).all()
            
            return [
                ProcessedNewsItem(
                    id=str(item.id),
                    title=item.title,
                    content=item.content,
                    url=item.url,
                    source=item.source,
                    source_type=SourceType(item.source_type),
                    published_at=item.published_at,
                    relevance_score=item.relevance_score,
                    keywords=item.keywords or [],
                    processed=item.processed,
                    published=item.published,
                    created_at=item.created_at,
                    summary=item.summary or "",
                    key_points=item.key_points or [],
                    sentiment=item.sentiment,
                    importance_level=item.importance_level,
                    formatted_content=item.formatted_content or "",
                    tags=item.tags or []
                )
                for item in db_items
            ]
    
    async def check_duplicate(self, url: str) -> bool:
        """Check if news item already exists"""
        with self.get_session() as session:
            existing = session.query(NewsItemDB).filter(NewsItemDB.url == url).first()
            return existing is not None
    
    async def get_stats(self) -> BotStats:
        """Get bot statistics"""
        with self.get_session() as session:
            total_collected = session.query(NewsItemDB).count()
            total_processed = session.query(NewsItemDB).filter(NewsItemDB.processed == True).count()
            total_published = session.query(NewsItemDB).filter(NewsItemDB.published == True).count()
            
            last_collection = session.query(NewsItemDB).order_by(NewsItemDB.created_at.desc()).first()
            last_collection_time = last_collection.created_at if last_collection else None
            
            return BotStats(
                total_news_collected=total_collected,
                total_news_processed=total_processed,
                total_news_published=total_published,
                last_collection_time=last_collection_time
            )
    
    # Redis operations for caching
    async def cache_news_item(self, key: str, data: Dict[str, Any], ttl: int = 3600):
        """Cache news item data"""
        self.redis.setex(key, ttl, json.dumps(data, default=str))
    
    async def get_cached_news_item(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached news item data"""
        cached = self.redis.get(key)
        if cached:
            return json.loads(cached)
        return None
    
    async def invalidate_cache(self, pattern: str):
        """Invalidate cache by pattern"""
        keys = self.redis.keys(pattern)
        if keys:
            self.redis.delete(*keys)

# Global database manager instance
db_manager = DatabaseManager()
