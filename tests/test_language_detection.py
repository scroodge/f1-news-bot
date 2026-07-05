"""Tests for language detection heuristics"""

from src.ai.content_processor import ContentProcessor


def test_detects_russian():
    p = ContentProcessor()
    assert p._detect_language("Ферстаппен выиграл гонку в Сильверстоуне") == "russian"


def test_detects_other_for_english():
    p = ContentProcessor()
    assert p._detect_language("Verstappen wins the race at Silverstone") == "other"


def test_mixed_mostly_english():
    p = ContentProcessor()
    assert p._detect_language("Grand Prix weekend schedule and results analysis ГП") == "other"


def test_empty_text_unknown():
    p = ContentProcessor()
    assert p._detect_language("12345 !!!") == "unknown"
