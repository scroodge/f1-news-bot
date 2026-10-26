"""Conservative story grouping: cited article identity or close headlines within 48 hours.

No text is discarded. Avoid transitive chains: every member must match the group anchor.
"""

import re
import uuid
from datetime import timedelta

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


def references(item) -> set[str]:
    return {
        canonical_url(r["url"])
        for r in (item.collection_info or {}).get("references", [])
        if r.get("kind") == "attribution" and r.get("url")
    }


def same_story(left, right) -> bool:
    if abs(to_naive_utc(left.published_at) - to_naive_utc(right.published_at)) > timedelta(
        hours=48
    ):
        return False
    lurl, rurl = canonical_url(left.url), canonical_url(right.url)
    lrefs, rrefs = references(left), references(right)
    if lurl == rurl or lurl in rrefs or rurl in lrefs or lrefs & rrefs:
        return True
    ltitle, rtitle = normalized_title(left.title), normalized_title(right.title)
    if ltitle == rtitle and len(ltitle.split()) >= 3:
        return True
    lt = set(ltitle.split()) - STOP_WORDS
    rt = set(rtitle.split()) - STOP_WORDS
    if len(lt) < 4 or len(rt) < 4:
        return False
    if set(re.findall(r"\d+", left.title)) != set(re.findall(r"\d+", right.title)):
        return False
    if bool(lt & {"not", "never", "no"}) != bool(rt & {"not", "never", "no"}):
        return False
    # Different drivers reacting to the same topic are complementary stories.
    ldrivers = {
        name
        for name in DRIVER_NAMES
        if len(name) > 3 and re.search(r"\b" + re.escape(name) + r"\b", left.title.lower())
    }
    rdrivers = {
        name
        for name in DRIVER_NAMES
        if len(name) > 3 and re.search(r"\b" + re.escape(name) + r"\b", right.title.lower())
    }
    if ldrivers and rdrivers and ldrivers.isdisjoint(rdrivers):
        return False
    locations = {
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
    if lt & locations and rt & locations and (lt & locations).isdisjoint(rt & locations):
        return False
    for positive, negative in CONTRASTS:
        if (lt & positive and rt & negative) or (rt & positive and lt & negative):
            return False
    return len(lt & rt) >= 4 and len(lt & rt) / len(lt | rt) >= 0.65


def assign_stories(items, recent):
    anchors = {}
    for old in recent:
        anchors.setdefault(old.story_id or old.id, old)
    for item in items:
        match = next((anchor for anchor in anchors.values() if same_story(item, anchor)), None)
        item.story_id = (match.story_id or match.id) if match else uuid.uuid4().hex
        anchors.setdefault(item.story_id, item)


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
