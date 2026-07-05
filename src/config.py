"""
Configuration management for F1 News Bot
"""

from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Comma-separated env values parsed into lists (NoDecode skips JSON parsing)
CommaSeparatedList = Annotated[list[str], NoDecode]

DEFAULT_RSS_FEEDS = [
    "https://www.f1news.ru/export/news.xml",
    "https://www.f1-world.ru/news/rssexp6.xml",
    "https://feeds.bbci.co.uk/sport/formula1/rss.xml",
]


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env"""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # Telegram Bot (publishing + admin)
    telegram_bot_token: str = ""
    telegram_channel_id: str = ""
    telegram_admin_id: str = ""

    # Telegram API (Telethon channel monitoring — user session)
    telegram_api_id: str = ""
    telegram_api_hash: str = ""
    telegram_phone: str = ""

    # Storage
    database_url: str = "postgresql://f1_user:f1_password@localhost:5432/f1_news"
    redis_url: str = "redis://localhost:6379/0"

    # LLM (remote Ollama-compatible server)
    llm_provider: str = "ollama"
    llm_base_url: str = "https://dev.offtech.by:8444/ollama"
    llm_model: str = "qwen2.5:14b"
    llm_embedding_model: str = "bge-m3:latest"
    llm_api_key: str = "ollama"
    llm_max_tokens: int = 512

    # Sources
    rss_feeds: CommaSeparatedList = DEFAULT_RSS_FEEDS
    telegram_channels: CommaSeparatedList = []

    # Processing
    check_interval_minutes: int = 30
    min_relevance_score: float = 0.1
    max_news_items_per_check: int = 50
    max_posts_per_hour: int = 5

    # Misc
    timezone: str = "Europe/Moscow"
    log_level: str = "INFO"
    log_file: str = "logs/f1_news_bot.log"
    debug: bool = False

    @field_validator("rss_feeds", "telegram_channels", mode="before")
    @classmethod
    def _split_comma_separated(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def database_url_async(self) -> str:
        """DATABASE_URL with the asyncpg driver for the app's async engine"""
        url = self.database_url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


# F1 Keywords for content filtering (English and Russian)
F1_KEYWORDS = [
    # English keywords
    "Formula 1",
    "F1",
    "Formula One",
    "Grand Prix",
    "GP",
    "racing",
    "race",
    "Hamilton",
    "Verstappen",
    "Leclerc",
    "Russell",
    "Sainz",
    "Perez",
    "Norris",
    "Mercedes",
    "Red Bull",
    "Ferrari",
    "McLaren",
    "Alpine",
    "Aston Martin",
    "AlphaTauri",
    "Alfa Romeo",
    "Williams",
    "Haas",
    "championship",
    "season",
    "qualifying",
    "pole position",
    "podium",
    "victory",
    "win",
    "driver",
    "constructor",
    "team",
    "car",
    "engine",
    "tire",
    "strategy",
    "pit stop",
    "safety car",
    "red flag",
    "yellow flag",
    "overtake",
    "crash",
    "accident",
    "penalty",
    "points",
    "leader",
    "standings",
    "circuit",
    "track",
    "lap",
    # Russian keywords
    "формула 1",
    "ф1",
    "формула один",
    "гран при",
    "гонка",
    "автогонки",
    "хамилтон",
    "верстаппен",
    "леклер",
    "расселл",
    "сайнс",
    "перес",
    "норрис",
    "мерседес",
    "ред булл",
    "феррари",
    "макларен",
    "альпин",
    "астон мартин",
    "альфатаури",
    "альфа ромео",
    "уильямс",
    "хаас",
    "чемпионат",
    "сезон",
    "квалификация",
    "поул позиция",
    "подиум",
    "победа",
    "победить",
    "пилот",
    "конструктор",
    "команда",
    "машина",
    "двигатель",
    "шина",
    "стратегия",
    "пит-стоп",
    "болид безопасности",
    "красный флаг",
    "желтый флаг",
    "обгон",
    "авария",
    "штраф",
    "очки",
    "лидер",
    "турнирная таблица",
    "трасса",
    "круг",
    "гонщик",
    "автогонщик",
]

# High-priority keywords that strongly indicate F1 content
HIGH_PRIORITY_KEYWORDS = [
    "formula 1",
    "f1",
    "формула 1",
    "ф1",
    "grand prix",
    "гран при",
    "racing",
    "гонка",
    "championship",
    "чемпионат",
    "verstappen",
    "верстаппен",
    "hamilton",
    "хамилтон",
    "ferrari",
    "феррари",
    "mercedes",
    "мерседес",
    "red bull",
    "ред булл",
]

# Team and driver names for better detection
TEAM_NAMES = [
    "mercedes",
    "мерседес",
    "red bull",
    "ред булл",
    "ferrari",
    "феррари",
    "mclaren",
    "макларен",
    "alpine",
    "альпин",
    "aston martin",
    "астон мартин",
    "alphatauri",
    "альфатаури",
    "alfa romeo",
    "альфа ромео",
    "williams",
    "уильямс",
    "haas",
    "хаас",
]

DRIVER_NAMES = [
    "hamilton",
    "хамилтон",
    "verstappen",
    "верстаппен",
    "leclerc",
    "леклер",
    "russell",
    "расселл",
    "sainz",
    "сайнс",
    "perez",
    "перес",
    "norris",
    "норрис",
    "alonso",
    "алонсо",
    "ocon",
    "окон",
    "gasly",
    "гасли",
    "tsunoda",
    "цунода",
    "bottas",
    "боттас",
    "zhou",
    "чжоу",
    "albon",
    "альбон",
    "latifi",
    "латифи",
    "schumacher",
    "шумахер",
    "magnussen",
    "магнуссен",
]

# Create settings instance
settings = Settings()
