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


class NewsStatus(StrEnum):
    """Lifecycle of a news item.

    collected -> processed -> queued -> published
                     \\-> rejected (by rules or by the admin)
    """

    COLLECTED = "collected"
    PROCESSED = "processed"
    QUEUED = "queued"
    PUBLISHED = "published"
    REJECTED = "rejected"


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
    status: NewsStatus = NewsStatus.COLLECTED
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Media fields
    image_url: str | None = None
    video_url: str | None = None
    media_type: str | None = None  # photo, video, document


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
    # Moderation / publication metadata
    rejected_reason: str | None = None
    telegram_message_id: int | None = None
    published_to_channel_at: datetime | None = None


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

    total_collected: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    published_today: int = 0
    published_this_week: int = 0
    last_collection_time: datetime | None = None


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
