"""Tests for semantic dedup math"""

from src.ai.dedup import cosine_similarity, find_duplicate


def test_identical_vectors():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_orthogonal_vectors():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_empty_or_mismatched():
    assert cosine_similarity([], [1.0]) == 0.0
    assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_find_duplicate_above_threshold():
    existing = [
        ("item-a", [1.0, 0.0, 0.0]),
        ("item-b", [0.9, 0.1, 0.0]),
    ]
    match = find_duplicate([1.0, 0.0, 0.0], existing, threshold=0.95)
    assert match is not None
    assert match[0] == "item-a"
    assert match[1] == 1.0


def test_find_duplicate_below_threshold():
    existing = [("item-a", [0.0, 1.0, 0.0])]
    assert find_duplicate([1.0, 0.0, 0.0], existing, threshold=0.9) is None


def test_find_duplicate_empty_history():
    assert find_duplicate([1.0, 0.0], [], threshold=0.9) is None
