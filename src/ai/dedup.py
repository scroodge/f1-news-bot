"""
Semantic dedup: catch the same story arriving from multiple sources.

bge-m3 embeddings are multilingual, so an English article and its Russian
retelling land close together in vector space. At this project's scale
(hundreds of items/week) cosine similarity in Python against recent items
is plenty — no pgvector needed.
"""

import logging
import math

logger = logging.getLogger(__name__)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def find_duplicate(
    embedding: list[float],
    existing: list[tuple[str, list[float]]],
    threshold: float,
) -> tuple[str, float] | None:
    """Return (item_id, similarity) of the closest match above threshold, else None"""
    best_id: str | None = None
    best_score = 0.0
    for item_id, other in existing:
        score = cosine_similarity(embedding, other)
        if score > best_score:
            best_id, best_score = item_id, score
    if best_id is not None and best_score >= threshold:
        return best_id, best_score
    return None
