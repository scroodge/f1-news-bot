"""
Data models for F1 News Bot
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

class SourceType(str, Enum):
    """Types of news sources"""
    RSS = "rss"
    TELEGRAM = "telegram"
    REDDIT = "reddit"
    TWITTER = "twitter"
    WEB = "web"

class NewsItem(BaseModel):
    """News item model"""
    id: Optional[str] = None
    title: str
    content: str
    url: str
    source: str
    source_type: SourceType
    published_at: datetime
    relevance_score: float = 0.0
    keywords: List[str] = Field(default_factory=list)
    processed: bool = False
    published: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Media fields
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    media_type: Optional[str] = None  # photo, video, document
    
    class Config:
        use_enum_values = False

class ProcessedNewsItem(NewsItem):
    """Processed news item with AI analysis"""
    summary: str
    key_points: List[str] = Field(default_factory=list)
    sentiment: str = "neutral"  # positive, negative, neutral
    importance_level: int = 1  # 1-5 scale
    formatted_content: str = ""
    tags: List[str] = Field(default_factory=list)
    # Translated content fields
    translated_title: Optional[str] = None
    translated_summary: Optional[str] = None
    translated_key_points: List[str] = Field(default_factory=list)
    original_language: Optional[str] = None

class PublishedNewsItem(ProcessedNewsItem):
    """Published news item with publication details"""
    published_at: datetime = Field(default_factory=datetime.utcnow)
    published_by: str = "telegram_bot"  # who published it
    telegram_message_id: Optional[int] = None  # Telegram message ID
    publication_status: str = "published"  # published, failed, scheduled
    views_count: int = 0
    engagement_count: int = 0

class TelegramChannel(BaseModel):
    """Telegram channel configuration"""
    channel_id: str
    channel_name: str
    username: Optional[str] = None
    is_active: bool = True
    keywords_filter: List[str] = Field(default_factory=list)
    min_relevance_score: float = 0.5

class RSSFeed(BaseModel):
    """RSS feed configuration"""
    url: str
    name: str
    is_active: bool = True
    check_interval: int = 15  # minutes
    last_checked: Optional[datetime] = None

class Stats(BaseModel):
    """Bot statistics"""
    total_news_collected: int = 0
    total_news_processed: int = 0
    total_news_published: int = 0
    last_collection_time: Optional[datetime] = None
    last_processing_time: Optional[datetime] = None
    last_publication_time: Optional[datetime] = None

class ProcessingResult(BaseModel):
    """Result of news processing"""
    success: bool
    news_item: Optional[ProcessedNewsItem] = None
    error_message: Optional[str] = None
    processing_time: float = 0.0

class PublicationResult(BaseModel):
    """Result of news publication"""
    success: bool
    message_id: Optional[str] = None
    error_message: Optional[str] = None
    publication_time: datetime = Field(default_factory=datetime.utcnow)