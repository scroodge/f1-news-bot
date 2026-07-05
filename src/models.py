"""
Data models for F1 News Bot
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SourceType(StrEnum):
    """Types of news sources"""

    RSS = "rss"
    TELEGRAM = "telegram"
    REDDIT = "reddit"
    TWITTER = "twitter"
    WEB = "web"


class NewsItem(BaseModel):
    """News item model"""

    id: str | None = None
    title: str
    content: str
    url: str
    source: str
    source_type: SourceType
    published_at: datetime
    relevance_score: float = 0.0
    keywords: list[str] = Field(default_factory=list)
    processed: bool = False
    published: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Media fields
    image_url: str | None = None
    video_url: str | None = None
    media_type: str | None = None  # photo, video, document

    class Config:
        use_enum_values = False


class ProcessedNewsItem(NewsItem):
    """Processed news item with AI analysis"""

    summary: str
    key_points: list[str] = Field(default_factory=list)
    sentiment: str = "neutral"  # positive, negative, neutral
    importance_level: int = 1  # 1-5 scale
    formatted_content: str = ""
    tags: list[str] = Field(default_factory=list)
    # Translated content fields
    translated_title: str | None = None
    translated_summary: str | None = None
    translated_key_points: list[str] = Field(default_factory=list)
    original_language: str | None = None


class PublishedNewsItem(ProcessedNewsItem):
    """Published news item with publication details"""

    published_at: datetime = Field(default_factory=datetime.utcnow)
    published_by: str = "telegram_bot"  # who published it
    telegram_message_id: int | None = None  # Telegram message ID
    publication_status: str = "published"  # published, failed, scheduled
    views_count: int = 0
    engagement_count: int = 0


class TelegramChannel(BaseModel):
    """Telegram channel configuration"""

    channel_id: str
    channel_name: str
    username: str | None = None
    is_active: bool = True
    keywords_filter: list[str] = Field(default_factory=list)
    min_relevance_score: float = 0.5


class RSSFeed(BaseModel):
    """RSS feed configuration"""

    url: str
    name: str
    is_active: bool = True
    check_interval: int = 15  # minutes
    last_checked: datetime | None = None


class Stats(BaseModel):
    """Bot statistics"""

    total_news_collected: int = 0
    total_news_processed: int = 0
    total_news_published: int = 0
    last_collection_time: datetime | None = None
    last_processing_time: datetime | None = None
    last_publication_time: datetime | None = None


class ProcessingResult(BaseModel):
    """Result of news processing"""

    success: bool
    news_item: ProcessedNewsItem | None = None
    error_message: str | None = None
    processing_time: float = 0.0


class PublicationResult(BaseModel):
    """Result of news publication"""

    success: bool
    message_id: str | None = None
    error_message: str | None = None
    publication_time: datetime = Field(default_factory=datetime.utcnow)
