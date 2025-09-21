"""
Configuration management for F1 News Bot
"""
import os
from typing import List, Optional
from pydantic import BaseSettings, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings(BaseSettings):
    """Application settings"""
    
    # Telegram Configuration
    telegram_api_id: int = Field(..., env="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(..., env="TELEGRAM_API_HASH")
    telegram_phone: str = Field(..., env="TELEGRAM_PHONE")
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    telegram_channel_id: str = Field(..., env="TELEGRAM_CHANNEL_ID")
    
    # Database Configuration
    database_url: str = Field(..., env="DATABASE_URL")
    redis_url: str = Field(..., env="REDIS_URL")
    
    # Ollama Configuration
    ollama_base_url: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama2", env="OLLAMA_MODEL")
    
    # External APIs
    reddit_client_id: Optional[str] = Field(default=None, env="REDDIT_CLIENT_ID")
    reddit_client_secret: Optional[str] = Field(default=None, env="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field(default="F1NewsBot/1.0", env="REDDIT_USER_AGENT")
    twitter_bearer_token: Optional[str] = Field(default=None, env="TWITTER_BEARER_TOKEN")
    
    # News Sources
    rss_feeds: List[str] = Field(
        default_factory=lambda: [
            "https://www.formula1.com/en/latest/all.xml",
            "https://www.motorsport.com/f1/rss/",
            "https://www.autosport.com/rss/"
        ],
        env="RSS_FEEDS"
    )
    
    # Monitoring Configuration
    check_interval_minutes: int = Field(default=15, env="CHECK_INTERVAL_MINUTES")
    max_posts_per_hour: int = Field(default=5, env="MAX_POSTS_PER_HOUR")
    min_relevance_score: float = Field(default=0.7, env="MIN_RELEVANCE_SCORE")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: str = Field(default="logs/f1_news_bot.log", env="LOG_FILE")
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Global settings instance
settings = Settings()

# F1 Keywords for relevance checking
F1_KEYWORDS = [
    "formula 1", "f1", "grand prix", "gp", "racing", "motorsport",
    "ferrari", "mercedes", "red bull", "mclaren", "alpine", "aston martin",
    "alfa romeo", "haas", "williams", "alpha tauri", "racing point",
    "hamilton", "verstappen", "leclerc", "sainz", "norris", "russell",
    "alonso", "ocon", "vettel", "stroll", "bottas", "zhou", "magnussen",
    "schumacher", "tsunoda", "gasly", "albon", "latifi", "de vries",
    "monaco", "silverstone", "spa", "monza", "interlagos", "suzuka",
    "qualifying", "race", "practice", "championship", "points", "podium"
]
