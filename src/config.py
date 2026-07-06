"""
Configuration management for F1 News Bot
"""

import logging
from pathlib import Path
from typing import Annotated

import yaml
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
    llm_provider: str = "ollama"  # "ollama" | "claude"
    llm_base_url: str = "https://dev.offtech.by:8444/ollama"
    llm_model: str = "qwen2.5:14b"
    llm_embedding_model: str = "bge-m3:latest"
    llm_api_key: str = "ollama"
    llm_max_tokens: int = 512

    # Claude API (preferred for Belarusian translation quality)
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5"

    # Sources
    rss_feeds: CommaSeparatedList = DEFAULT_RSS_FEEDS
    telegram_channels: CommaSeparatedList = []

    # Processing
    check_interval_minutes: int = 30
    min_relevance_score: float = 0.1
    max_news_items_per_check: int = 50
    max_posts_per_hour: int = 5

    # Semantic dedup (embeddings via the Ollama server)
    dedup_enabled: bool = True
    dedup_similarity_threshold: float = 0.90
    dedup_lookback_days: int = 7

    # Telegram Mini App (admin panel)
    # Public HTTPS URL of the Mini App (Telegram requires TLS); empty = no button
    miniapp_url: str = ""
    # DANGER: skips Telegram auth for local browser testing. Never in production.
    miniapp_dev_mode: bool = False

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


# --- F1 domain data ---------------------------------------------------------
# Loaded from data/f1_2026.yaml (teams/drivers/keywords in en/ru/be forms).
# Edit the YAML when the grid changes; these lists drive relevance scoring.

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "f1_2026.yaml"

# Minimal fallback so the app still runs if the data file is missing
_FALLBACK_KEYWORDS = ["formula 1", "f1", "grand prix", "формула 1", "ф1", "гран при"]


def _load_domain_data() -> tuple[list[str], list[str], list[str], list[str]]:
    try:
        with open(_DATA_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        general = [k.lower() for k in data["keywords"]["general"]]
        high_priority = [k.lower() for k in data["keywords"]["high_priority"]]
        teams = [name.lower() for team in data["teams"] for name in team["names"]]
        drivers = [name.lower() for driver in data["drivers"] for name in driver["names"]]
        keywords = list(dict.fromkeys(general + teams + drivers))
        return keywords, high_priority, teams, drivers
    except Exception as e:  # pragma: no cover - defensive
        logging.getLogger(__name__).error(f"Failed to load {_DATA_FILE}: {e} — using fallback")
        return _FALLBACK_KEYWORDS, _FALLBACK_KEYWORDS, [], []


F1_KEYWORDS, HIGH_PRIORITY_KEYWORDS, TEAM_NAMES, DRIVER_NAMES = _load_domain_data()

# Create settings instance
settings = Settings()
