"""Tests for the structured analysis schemas"""

from src.ai.schemas import KeyPointsAnalysis, NewsAnalysis


def test_valid_analysis_parses():
    a = NewsAnalysis.model_validate_json(
        '{"title_be": "Ферстапен выйграў Гран-пры", "summary_be": "Кароткі пераказ.",'
        ' "key_points_be": ["перамога"], "sentiment": "positive",'
        ' "importance_level": 4, "tags_be": ["гонка"]}'
    )
    assert a.title_be.startswith("Ферстапен")
    assert a.importance_level == 4


def test_importance_clamped():
    assert NewsAnalysis(title_be="t", summary_be="s", importance_level=99).importance_level == 5
    assert NewsAnalysis(title_be="t", summary_be="s", importance_level=-3).importance_level == 1
    assert NewsAnalysis(title_be="t", summary_be="s", importance_level="junk").importance_level == 1


def test_lists_limited():
    a = NewsAnalysis(
        title_be="t",
        summary_be="s",
        key_points_be=["1", "2", "3", "4", "5"],
        tags_be=["a", "b", "c", "d", "e", "f", "g"],
    )
    assert len(a.key_points_be) == 3
    assert len(a.tags_be) == 5


def test_defaults():
    a = NewsAnalysis(title_be="t", summary_be="s")
    assert a.sentiment == "neutral"
    assert a.importance_level == 1
    assert a.key_points_be == []


def test_key_points_analysis_parses():
    k = KeyPointsAnalysis.model_validate_json(
        '{"key_points_be": ["Ферстапен перамог у гонцы", "Хэмілтан фінішаваў другім"]}'
    )
    assert len(k.key_points_be) == 2
    assert "Ферстапен" in k.key_points_be[0]


def test_key_points_analysis_defaults():
    k = KeyPointsAnalysis()
    assert k.key_points_be == []
