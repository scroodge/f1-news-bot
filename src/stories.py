"""Conservative story grouping: cited article identity or close headlines within 48 hours.

No text is discarded. Avoid transitive chains: every member must match the group anchor.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import DRIVER_NAMES
from .editorial import canonical_url, editorial_priority, normalized_title
from .utils.timezone import to_naive_utc

STOP_WORDS = set(
    [
        "a",
        "an",
        "the",
        "on",
        "in",
        "at",
        "of",
        "to",
        "for",
        "and",
        "or",
        "with",
        "by",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "f1",
        "formula",
        "1",
        "says",
        "said",
    ]
)
# A shared driver alone must not merge unrelated events. Opposite developments stay separate.
CONTRASTS = (
    ({"join", "joins", "signs", "signed"}, {"leaves", "leave", "exit", "exits"}),
    ({"denies", "denied", "dismisses"}, {"confirms", "confirmed", "announces"}),
    ({"wins", "win", "victory"}, {"loses", "loss", "defeat"}),
    (
        {"reveals", "reveal", "introduces", "introduce"},
        {"delays", "delay", "postpones", "postpone"},
    ),
)
LOCATIONS = {
    "mexico",
    "brazil",
    "austin",
    "monza",
    "silverstone",
    "spa",
    "baku",
    "monaco",
    "singapore",
    "miami",
    "suzuka",
    "qatar",
    "bahrain",
    "jeddah",
    "madrid",
    "barcelona",
    "imola",
    "hungary",
    "austria",
    "australia",
    "china",
    "canada",
    "zandvoort",
    "vegas",
    "dhabi",
}
NEGATIONS = {"not", "never", "no"}
STORY_WINDOW = timedelta(hours=48)
# Compiled once: matching every driver per pair made grouping O(pairs × drivers) regex calls.
DRIVER_PATTERNS = [
    (name, re.compile(r"\b" + re.escape(name) + r"\b")) for name in DRIVER_NAMES if len(name) > 3
]


def references(item) -> set[str]:
    return {
        canonical_url(r["url"])
        for r in (item.collection_info or {}).get("references", [])
        if r.get("kind") == "attribution" and r.get("url")
    }


@dataclass(frozen=True)
class _Features:
    """Per-item values that same_story compares; computed once per item, not per pair."""

    published_at: datetime
    url: str
    refs: frozenset[str]
    title: str
    tokens: frozenset[str]
    numbers: frozenset[str]
    negated: bool
    drivers: frozenset[str]
    locations: frozenset[str]


def _features(item) -> _Features:
    title = normalized_title(item.title)
    tokens = frozenset(title.split()) - STOP_WORDS
    lower = item.title.lower()
    return _Features(
        published_at=to_naive_utc(item.published_at),
        url=canonical_url(item.url),
        refs=frozenset(references(item)),
        title=title,
        tokens=tokens,
        numbers=frozenset(re.findall(r"\d+", item.title)),
        negated=bool(tokens & NEGATIONS),
        drivers=frozenset(name for name, pattern in DRIVER_PATTERNS if pattern.search(lower)),
        locations=tokens & LOCATIONS,
    )


def _same(left: _Features, right: _Features) -> bool:
    if abs(left.published_at - right.published_at) > STORY_WINDOW:
        return False
    if (
        left.url == right.url
        or left.url in right.refs
        or right.url in left.refs
        or left.refs & right.refs
    ):
        return True
    if left.title == right.title and len(left.title.split()) >= 3:
        return True
    lt, rt = left.tokens, right.tokens
    if len(lt) < 4 or len(rt) < 4:
        return False
    if left.numbers != right.numbers or left.negated != right.negated:
        return False
    # Different drivers reacting to the same topic are complementary stories.
    if left.drivers and right.drivers and left.drivers.isdisjoint(right.drivers):
        return False
    if left.locations and right.locations and left.locations.isdisjoint(right.locations):
        return False
    for positive, negative in CONTRASTS:
        if (lt & positive and rt & negative) or (rt & positive and lt & negative):
            return False
    shared = len(lt & rt)
    return shared >= 4 and shared / len(lt | rt) >= 0.65


def same_story(left, right) -> bool:
    return _same(_features(left), _features(right))


def assign_stories(items, recent):
    """CPU-bound for large `recent`; call via asyncio.to_thread from async code."""
    anchors: dict[str, _Features] = {}
    for old in recent:
        key = old.story_id or old.id
        if key not in anchors:
            anchors[key] = _features(old)
    for item in items:
        features = _features(item)
        match = next((key for key, anchor in anchors.items() if _same(features, anchor)), None)
        item.story_id = match or uuid.uuid4().hex
        anchors.setdefault(item.story_id, features)


def representative(items):
    cited = set().union(*(references(item) for item in items))
    return max(
        items,
        key=lambda item: (
            canonical_url(item.url) in cited,
            (item.collection_info or {}).get("text_quality") == "article",
            editorial_priority(item),
            -to_naive_utc(item.published_at).timestamp(),
            item.id or item.url,
        ),
    )
