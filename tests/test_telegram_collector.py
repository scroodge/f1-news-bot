from src.collectors import telegram_collector
from src.collectors.telegram_collector import TelegramCollector


def _configure(monkeypatch, api_id, api_hash, phone, channels):
    s = telegram_collector.settings
    monkeypatch.setattr(s, "telegram_api_id", api_id)
    monkeypatch.setattr(s, "telegram_api_hash", api_hash)
    monkeypatch.setattr(s, "telegram_phone", phone)
    monkeypatch.setattr(s, "telegram_channels", channels)


def test_placeholders_disable_collector(monkeypatch):
    _configure(
        monkeypatch,
        "your_api_id_here",
        "your_api_hash_here",
        "your_phone_number_here",
        ["@f1channel1", "@f1channel2"],
    )
    assert TelegramCollector().enabled is False


def test_no_channels_disables_collector(monkeypatch):
    _configure(monkeypatch, "12345", "abcdef", "+375290000000", [])
    assert TelegramCollector().enabled is False


def test_real_config_enables_collector(monkeypatch):
    _configure(monkeypatch, "12345", "abcdef", "+375290000000", ["@realchannel"])
    assert TelegramCollector().enabled is True


async def test_disabled_collector_skips_client(monkeypatch):
    _configure(monkeypatch, "", "", "", [])
    collector = TelegramCollector()
    await collector.initialize()
    assert collector.client is None
    assert await collector.collect_news() == []
