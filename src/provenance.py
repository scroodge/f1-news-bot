"""Article evidence extracted from publisher HTML, without an LLM or link crawling."""

import json
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .editorial import SOURCE_PRIORITIES, canonical_url

ATTRIBUTION = re.compile(
    r"according to|reported by|reports? from|told|speaking (?:exclusively )?to|"
    r"interview (?:with|by)|via|first reported|has learned|has learnt",
    re.I,
)
PAYWALL_TEXT = re.compile(
    r"subscribe to (?:continue|read|unlock)|sign in to (?:continue|read)|"
    r"this (?:article|content) is (?:only |exclusively )?for (?:subscribers|members)",
    re.I,
)


def article_url(url: str) -> bool:
    """Only known public publishers and article-like paths; never follow arbitrary feed URLs."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").removeprefix("www.")
        if (
            parts.scheme != "https"
            or parts.port not in (None, 443)
            or parts.username
            or parts.password
        ):
            return False
        if host not in SOURCE_PRIORITIES:
            return False
        path = parts.path.rstrip("/")
        if not path or any(
            p in path for p in ("/author/", "/category/", "/tag/", "/info/", "/about", "/rss/")
        ):
            return False
        segments = path.split("/")
        if host in {"bbc.com", "bbc.co.uk"}:
            return bool(re.fullmatch(r"/sport/formula1/(?:articles/[a-z0-9]{8,}|[0-9]{6,})", path))
        slug = segments[-2] if segments[-1].isdigit() and len(segments) > 2 else segments[-1]
        return len(slug) >= 15 and "-" in slug
    except ValueError:
        return False


def references_from_html(html: str, url: str, *, fragment: bool = False) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    root = soup if fragment else soup.find("article") or soup.find("main")
    if root is None:
        return []
    references = []
    seen = set()
    for anchor in root.find_all("a", href=True):
        # Related-story widgets and nav links are not attribution.
        if anchor.find_parent(["aside", "nav", "footer", "header"]):
            continue
        paragraph = anchor.find_parent("p")
        if paragraph is None and fragment and anchor.parent is root:
            paragraph = root
        if paragraph is None:
            continue
        context = paragraph.get_text(" ", strip=True)
        if len(context) > 1500 or not ATTRIBUTION.search(context):
            continue
        target = canonical_url(urljoin(url, anchor["href"]))
        if not article_url(target) or target == canonical_url(url) or target in seen:
            continue
        if urlsplit(target).hostname == urlsplit(url).hostname:
            continue
        seen.add(target)
        references.append(
            {
                "url": target,
                "source": urlsplit(target).hostname,
                "evidence": context[:500],
                "kind": "attribution",
            }
        )
        if len(references) == 5:
            break
    return references


def _restricted(value) -> bool:
    if isinstance(value, dict):
        if value.get("isAccessibleForFree") in (False, "False", "false"):
            return True
        return any(_restricted(v) for v in value.values())
    if isinstance(value, list):
        return any(_restricted(v) for v in value)
    return False


def text_evidence(text: str, origin: str, html: str = "") -> dict:
    soup = BeautifulSoup(html, "html.parser")
    restricted = False
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            restricted |= _restricted(json.loads(script.get_text()))
        except (ValueError, TypeError):
            continue
    restricted |= bool(PAYWALL_TEXT.search(text))
    if restricted:
        quality = "paywall"
    elif origin == "rss_summary":
        quality = "teaser"
    elif len(text.strip()) < 800:
        quality = "short"
    elif origin == "article":
        quality = "article"
    else:
        quality = "unverified"
    return {"text_quality": quality, "text_origin": origin, "text_chars": len(text.strip())}


QUALITY_LABELS = {
    "article": "Тэкст са старонкі артыкула",
    "teaser": "Даступны толькі RSS-анонс",
    "paywall": "Магчымая платная або абмежаваная публікацыя",
    "short": "Кароткі тэкст: паўната не пацверджана",
    "unverified": "Паўната тэксту не пацверджана",
    "unknown": "Паўната тэксту невядомая",
}


def quality_info(item) -> dict:
    evidence = item.collection_info or {}
    quality = evidence.get("text_quality", "unknown")
    return {
        "status": quality,
        "label": QUALITY_LABELS.get(quality, QUALITY_LABELS["unknown"]),
        "characters": len(item.content),
        "needs_confirmation": quality != "article",
    }


PUBLISHER_NAMES = {
    "autosport.com": r"Autosport",
    "motorsport.com": r"Motorsport\.com",
    "the-race.com": r"The Race",
    "bbc.co.uk": r"BBC(?: Sport)?",
    "skysports.com": r"Sky Sports(?: F1)?",
    "racingnews365.com": r"RacingNews365",
    "planetf1.com": r"PlanetF1(?:\.com)?",
    "formula1.com": r"(?:Formula1|F1)\.com",
}


def named_attributions(text: str, url: str) -> list[dict]:
    """Keep publisher names even when no actual article link was supplied."""
    own_host = (urlsplit(url).hostname or "").removeprefix("www.")
    found = []
    for host, name in PUBLISHER_NAMES.items():
        if host == own_host:
            continue
        match = re.search(
            r"(?:according to|reported by|told|speaking (?:exclusively )?to|via)\s+" + name + r"\b",
            text,
            re.I,
        )
        if match:
            found.append(
                {
                    "source": host,
                    "evidence": text[max(0, match.start() - 40) : match.end() + 100].strip(),
                }
            )
    return found
