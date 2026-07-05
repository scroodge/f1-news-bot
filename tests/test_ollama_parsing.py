"""Tests for parsing LLM responses"""

from src.ai.ollama_client import OllamaClient


def make_client() -> OllamaClient:
    return OllamaClient()


def test_parses_clean_json():
    c = make_client()
    result = c._parse_ollama_response(
        '{"summary": "Ферстаппен выиграл гонку", "key_points": ["поул", "победа"],'
        ' "sentiment": "positive", "importance_level": 4, "tags": ["гонка"]}'
    )
    assert result["summary"] == "Ферстаппен выиграл гонку"
    assert result["importance_level"] == 4
    assert result["key_points"] == ["поул", "победа"]


def test_parses_json_embedded_in_prose():
    c = make_client()
    result = c._parse_ollama_response(
        'Вот результат анализа:\n{"summary": "Новость о Феррари", "key_points": [],'
        ' "sentiment": "neutral", "importance_level": 2, "tags": []}\nНадеюсь, это помогло!'
    )
    assert result["summary"] == "Новость о Феррари"
    assert result["importance_level"] == 2


def test_garbage_returns_fallback():
    c = make_client()
    result = c._parse_ollama_response("совершенно не JSON ответ без фигурных скобок")
    # Fallback must still produce a usable dict
    assert isinstance(result, dict)
    assert "summary" in result
    assert "importance_level" in result
