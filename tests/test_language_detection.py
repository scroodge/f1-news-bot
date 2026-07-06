"""Tests for source-language detection heuristics"""

from src.ai.content_processor import ContentProcessor


def make_processor() -> ContentProcessor:
    return ContentProcessor()


def test_detects_russian():
    p = make_processor()
    assert p._detect_language("Ферстаппен выиграл гонку в Сильверстоуне") == "ru"


def test_detects_belarusian():
    p = make_processor()
    assert p._detect_language("Ферстапен выйграў гонку ў Сільверстоўне") == "be"


def test_detects_english():
    p = make_processor()
    assert p._detect_language("Verstappen wins the race at Silverstone") == "en"


def test_mixed_mostly_english():
    p = make_processor()
    assert p._detect_language("Grand Prix weekend schedule and results analysis ГП") == "en"


def test_no_letters_unknown():
    p = make_processor()
    assert p._detect_language("12345 !!!") == "unknown"
