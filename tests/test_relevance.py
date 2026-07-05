"""Tests for keyword relevance scoring in BaseCollector"""

from src.collectors.rss_collector import RSSCollector


def make_collector() -> RSSCollector:
    return RSSCollector()


def test_f1_news_scores_high():
    c = make_collector()
    score = c.calculate_relevance_score(
        "Verstappen takes pole position at the British Grand Prix",
        "Red Bull driver Max Verstappen beat Lando Norris in qualifying for the Formula 1 race.",
    )
    assert score >= 0.5


def test_unrelated_news_scores_zero():
    c = make_collector()
    # NB: keyword matching is substring-based, so generic words like
    # "win"/"race"/"car" would still match — known scorer weakness (Phase 2)
    score = c.calculate_relevance_score(
        "Stock markets fall on tech earnings",
        "Investors sold shares amid uncertainty about interest rates.",
    )
    assert score == 0.0


def test_russian_f1_news_scores():
    c = make_collector()
    score = c.calculate_relevance_score(
        "Ферстаппен выиграл квалификацию Гран При",
        "Пилот Ред Булл завоевал поул позицию, феррари осталась второй.",
    )
    assert score >= 0.5


def test_score_bounded():
    c = make_collector()
    text = " ".join(["formula 1 verstappen hamilton ferrari mercedes grand prix"] * 20)
    assert c.calculate_relevance_score(text, text) <= 1.0


def test_extract_keywords_dedup():
    c = make_collector()
    keywords = c.extract_keywords("Ferrari Ferrari Ferrari", "ferrari wins the race")
    assert len(keywords) == len(set(keywords))
    assert any("ferrari" in k.lower() for k in keywords)
