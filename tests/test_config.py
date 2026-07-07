"""Tests for Settings parsing"""

from src.config import Settings


def test_comma_separated_lists_from_env(monkeypatch):
    monkeypatch.setenv("RSS_FEEDS", "https://a.example/rss, https://b.example/rss ,")
    monkeypatch.setenv("TELEGRAM_CHANNELS", "@one,@two")
    s = Settings(_env_file=None)
    assert s.rss_feeds == ["https://a.example/rss", "https://b.example/rss"]
    assert s.telegram_channels == ["@one", "@two"]


def test_defaults_without_env(monkeypatch):
    for var in ("RSS_FEEDS", "TELEGRAM_CHANNELS", "LLM_MODEL"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert len(s.rss_feeds) == 3
    assert s.telegram_channels == []
    assert s.llm_provider == "ollama"
    assert s.llm_model == "qwen2.5:14b"
    assert s.llm_embedding_model == "bge-m3:latest"
    assert s.llm_max_tokens == 2048


def test_llm_settings_from_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example/ollama")
    monkeypatch.setenv("LLM_MAX_TOKENS", "256")
    s = Settings(_env_file=None)
    assert s.llm_base_url == "https://llm.example/ollama"
    assert s.llm_max_tokens == 256
