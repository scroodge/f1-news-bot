"""Transparent editorial heuristics, separate from F1 relevance.

These signals help moderation; they do not verify exclusivity or truth.
Keep SQL and Python scoring identical so pagination matches the displayed score.
"""

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import case, func

SOURCE_PRIORITIES = {
    "the-race.com": 4,
    "autosport.com": 4,
    "bbc.co.uk": 4,
    "bbc.com": 4,
    "skysports.com": 4,
    "racingnews365.com": 3,
    "motorsport.com": 3,
    "formula1.com": 2,
    "planetf1.com": 2,
    "gpblog.com": 1,
}
ORIGINAL_SIGNALS = ("exclusive interview", "speaking exclusively", "our sources", "we understand")
SECONDARY_SIGNALS = ("according to reports", "reports claiming", "as reported by")


def canonical_url(url: str) -> str:
    """Remove tracking parameters, preserving query parameters with article identity."""
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
    ]
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), "")
    )


def editorial_priority(item) -> int:
    host = (urlsplit(item.url).hostname or "").removeprefix("www.")
    score = SOURCE_PRIORITIES.get(host, 0)
    text = f"{item.title} {item.content}".lower()
    if any(signal in text for signal in ORIGINAL_SIGNALS):
        score += 2
    if any(signal in text for signal in SECONDARY_SIGNALS):
        score -= 2
    return score


def editorial_priority_sql(model):
    url = func.lower(model.url)
    text = func.lower(model.title + " " + model.content)
    source = case(
        *[
            (url.like(f"https://{prefix}{host}/%"), priority)
            for host, priority in SOURCE_PRIORITIES.items()
            for prefix in ("", "www.")
        ],
        else_=0,
    )
    original = case(
        (text.contains(ORIGINAL_SIGNALS[0]), 2),
        *[(text.contains(s), 2) for s in ORIGINAL_SIGNALS[1:]],
        else_=0,
    )
    secondary = case(*[(text.contains(s), 2) for s in SECONDARY_SIGNALS], else_=0)
    return source + original - secondary


def normalized_title(title: str) -> str:
    return " ".join(re.findall(r"\w+", title.lower()))


def editorial_reasons(item) -> list[dict]:
    host = (urlsplit(item.url).hostname or "").removeprefix("www.")
    text = f"{item.title} {item.content}".lower()
    reasons = [
        {
            "code": "source",
            "label": f"Прыярытэт крыніцы: {SOURCE_PRIORITIES.get(host, 0)}",
            "evidence": host,
        }
    ]
    originals = [s for s in ORIGINAL_SIGNALS if s in text]
    secondary = [s for s in SECONDARY_SIGNALS if s in text]
    if originals:
        reasons.append(
            {
                "code": "original_signal",
                "label": "Прыкметы ўласнага матэрыялу (+2)",
                "evidence": ", ".join(originals),
            }
        )
    if secondary:
        reasons.append(
            {
                "code": "secondary_signal",
                "label": "Прыкметы пераказу (−2)",
                "evidence": ", ".join(secondary),
            }
        )
    if (item.collection_info or {}).get("references"):
        reasons.append(
            {"code": "attribution", "label": "Ёсць спасылка на іншае выданне", "evidence": ""}
        )
    return reasons
