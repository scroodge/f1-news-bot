"""
Configuration management for F1 News Bot
"""
import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, model_validator, BeforeValidator
from typing import Annotated
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def parse_comma_separated_list(v):
    """Parse comma-separated string to list"""
    if isinstance(v, str):
        return [item.strip() for item in v.split(',') if item.strip()]
    return v

class Settings(BaseSettings):
    """Application settings"""
    
    # Telegram Bot Configuration
    telegram_bot_token: str = Field(default="", env="TELEGRAM_BOT_TOKEN")
    telegram_channel_id: str = Field(default="", env="TELEGRAM_CHANNEL_ID")
    telegram_admin_id: str = Field(default="", env="TELEGRAM_ADMIN_ID")
    
    # Telegram API Configuration (for channel monitoring)
    telegram_api_id: str = Field(default="", env="TELEGRAM_API_ID")
    telegram_api_hash: str = Field(default="", env="TELEGRAM_API_HASH")
    telegram_phone: str = Field(default="", env="TELEGRAM_PHONE")
    
    # Database Configuration
    database_url: str = Field(
        default="postgresql://f1_user:f1_password@localhost:5432/f1_news",
        env="DATABASE_URL"
    )
    redis_url: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    
    # Ollama Configuration
    ollama_base_url: str = Field(default="http://localhost:11434", env="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama2", env="OLLAMA_MODEL")
    
    # Reddit Configuration
    reddit_client_id: str = Field(default="", env="REDDIT_CLIENT_ID")
    reddit_client_secret: str = Field(default="", env="REDDIT_CLIENT_SECRET")
    reddit_user_agent: str = Field(default="F1NewsBot/1.0", env="REDDIT_USER_AGENT")
    
    # Twitter Configuration
    twitter_api_key: str = Field(default="", env="TWITTER_API_KEY")
    twitter_api_secret: str = Field(default="", env="TWITTER_API_SECRET")
    twitter_access_token: str = Field(default="", env="TWITTER_ACCESS_TOKEN")
    twitter_access_token_secret: str = Field(default="", env="TWITTER_ACCESS_TOKEN_SECRET")
    
    # RSS Feeds (as string from env, parsed to list)
    rss_feeds_str: str = Field(
        default="https://www.f1news.ru/export/news.xml,https://www.f1-world.ru/news/rssexp6.xml,https://feeds.bbci.co.uk/sport/formula1/rss.xml",
        env="RSS_FEEDS"
    )
    
    @property
    def rss_feeds(self) -> List[str]:
        """Parse RSS feeds from comma-separated string"""
        if self.rss_feeds_raw:
            return parse_comma_separated_list(self.rss_feeds_raw)
        return parse_comma_separated_list(self.rss_feeds_str)
    
    @property
    def telegram_channels(self) -> List[str]:
        """Parse Telegram channels from comma-separated string"""
        if self.telegram_channels_raw:
            return parse_comma_separated_list(self.telegram_channels_raw)
        return []
    
    # Processing Configuration
    check_interval_minutes: int = Field(default=30, env="CHECK_INTERVAL_MINUTES")
    min_relevance_score: float = Field(default=0.7, env="MIN_RELEVANCE_SCORE")
    max_news_items_per_check: int = Field(default=50, env="MAX_NEWS_ITEMS_PER_CHECK")
    max_posts_per_hour: int = Field(default=5, env="MAX_POSTS_PER_HOUR")
    
    # Logging Configuration
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: str = Field(default="logs/f1_news_bot.log", env="LOG_FILE")
    
    # Debug mode
    debug: bool = Field(default=False, env="DEBUG")
    
    # Additional fields from .env
    twitter_bearer_token: str = Field(default="", env="TWITTER_BEARER_TOKEN")
    test_mode: bool = Field(default=False, env="TEST_MODE")
    use_mock_data: bool = Field(default=False, env="USE_MOCK_DATA")
    
    # Raw fields from .env (to avoid JSON parsing)
    rss_feeds_raw: str = Field(default="", env="RSS_FEEDS")
    telegram_channels_raw: str = Field(default="", env="TELEGRAM_CHANNELS")
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from .env

# F1 Keywords for content filtering (English and Russian)
F1_KEYWORDS = [
    # English keywords
    "Formula 1", "F1", "Formula One", "Grand Prix", "GP", "racing", "race",
    "Hamilton", "Verstappen", "Leclerc", "Russell", "Sainz", "Perez", "Norris",
    "Mercedes", "Red Bull", "Ferrari", "McLaren", "Alpine", "Aston Martin",
    "AlphaTauri", "Alfa Romeo", "Williams", "Haas", "championship", "season",
    "qualifying", "pole position", "podium", "victory", "win", "driver",
    "constructor", "team", "car", "engine", "tire", "strategy", "pit stop",
    "safety car", "red flag", "yellow flag", "overtake", "crash", "accident",
    "penalty", "points", "leader", "standings", "circuit", "track", "lap",
    
    # Russian keywords
    "формула 1", "ф1", "формула один", "гран при", "гонка", "автогонки",
    "хамилтон", "верстаппен", "леклер", "расселл", "сайнс", "перес", "норрис",
    "мерседес", "ред булл", "феррари", "макларен", "альпин", "астон мартин",
    "альфатаури", "альфа ромео", "уильямс", "хаас", "чемпионат", "сезон",
    "квалификация", "поул позиция", "подиум", "победа", "победить", "пилот",
    "конструктор", "команда", "машина", "двигатель", "шина", "стратегия",
    "пит-стоп", "болид безопасности", "красный флаг", "желтый флаг",
    "обгон", "авария", "штраф", "очки", "лидер", "турнирная таблица",
    "трасса", "круг", "гонщик", "автогонщик"
]

# High-priority keywords that strongly indicate F1 content
HIGH_PRIORITY_KEYWORDS = [
    "formula 1", "f1", "формула 1", "ф1", "grand prix", "гран при",
    "racing", "гонка", "championship", "чемпионат", "verstappen", "верстаппен",
    "hamilton", "хамилтон", "ferrari", "феррари", "mercedes", "мерседес",
    "red bull", "ред булл"
]

# Team and driver names for better detection
TEAM_NAMES = [
    "mercedes", "мерседес", "red bull", "ред булл", "ferrari", "феррари",
    "mclaren", "макларен", "alpine", "альпин", "aston martin", "астон мартин",
    "alphatauri", "альфатаури", "alfa romeo", "альфа ромео", "williams", "уильямс",
    "haas", "хаас"
]

DRIVER_NAMES = [
    "hamilton", "хамилтон", "verstappen", "верстаппен", "leclerc", "леклер",
    "russell", "расселл", "sainz", "сайнс", "perez", "перес", "norris", "норрис",
    "alonso", "алонсо", "ocon", "окон", "gasly", "гасли", "tsunoda", "цунода",
    "bottas", "боттас", "zhou", "чжоу", "albon", "альбон", "latifi", "латифи",
    "schumacher", "шумахер", "magnussen", "магнуссен"
]

# Create settings instance
settings = Settings()