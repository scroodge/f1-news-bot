"""Versioned, deterministic shadow baseline and immutable feedback payloads.

This module never calls a model or changes an item's lifecycle. Its suggestions
are training/evaluation inputs, not permission to translate or publish.
"""

import hashlib
import json
import re
from difflib import unified_diff
from functools import lru_cache
from pathlib import Path

from .config import settings
from .editorial import editorial_priority
from .provenance import quality_info

POLICY_VERSION = "shadow-rules-v1"
REASON_LABELS = {
    "unspecified": "Прычына не пазначана",
    "interesting": "Цікавы матэрыял",
    "original_source": "Уласны матэрыял / першакрыніца",
    "duplicate": "Дублікат",
    "low_novelty": "Мала новых фактаў",
    "not_interesting": "Нецікава для канала",
    "outdated": "Састарэла",
    "unverified": "Непацверджаныя звесткі",
    "incomplete": "Няпоўны тэкст",
    "factual_error": "Памылка ў фактах",
    "translation_error": "Памылка перакладу",
    "attribution_error": "Памылка атрыбуцыі",
    "style": "Стыль / мова",
    "capacity": "Ліміт публікацый",
    "other": "Іншае",
}
RISK_PATTERN = re.compile(
    r"\brumou?rs?\b|\bunconfirmed\b|\balleg(?:ed|ation)s?\b|\breportedly\b", re.I
)
SNAPSHOT_FIELDS = (
    "title",
    "content",
    "url",
    "source",
    "source_type",
    "published_at",
    "story_id",
    "collection_info",
    "relevance_score",
    "keywords",
    "status",
    "created_at",
    "summary",
    "translated_title",
    "translated_summary",
    "key_points",
    "translated_key_points",
    "tags",
    "sentiment",
    "importance_level",
    "original_language",
    "formatted_content",
    "llm_usage",
    "rejected_reason",
)
SOURCE_FIELDS = (
    "title",
    "content",
    "url",
    "source",
    "source_type",
    "published_at",
    "collection_info",
)
DRAFT_FIELDS = (
    "summary",
    "translated_title",
    "translated_summary",
    "key_points",
    "tags",
    "importance_level",
)


def stable_hash(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def snapshot(item) -> dict:
    return json.loads(json.dumps({k: getattr(item, k, None) for k in SNAPSHOT_FIELDS}, default=str))


def shadow_recommendation(item) -> dict:
    """Conservative baseline, explicitly untrained; publication always needs a human."""
    quality = quality_info(item)
    priority = editorial_priority(item)
    reasons = []
    if quality["needs_confirmation"]:
        selection = "human_review"
        reasons.append(quality["label"])
    elif RISK_PATTERN.search(f"{item.title} {item.content}"):
        selection = "human_review"
        reasons.append("Ёсць прыкметы непацверджаных або спрэчных звестак")
    elif priority >= 3 and item.relevance_score >= settings.min_relevance_score:
        selection = "translate"
        reasons.append("Прыярытэтная крыніца і тэматычна рэлевантны артыкул")
    else:
        selection = "skip"
        reasons.append("Недастаткова сігналаў для прыярытэтнага перакладу")
    inputs = {k: getattr(item, k, None) for k in SOURCE_FIELDS}
    inputs.update(
        relevance=item.relevance_score,
        min_relevance=settings.min_relevance_score,
        priority=priority,
    )
    return {
        "mode": "shadow",
        "engine": "rules",
        "policy_version": POLICY_VERSION,
        "policy_hash": policy_code_hash(),
        "input_hash": stable_hash(inputs),
        "selection": selection,
        "publication": "human_review",
        "reasons": reasons,
        "automatic_actions": False,
    }


def changes_between(before: dict | None, after: dict | None) -> dict:
    if before is None or after is None:
        return {}
    result = {}
    for field in before.keys() | after.keys():
        old, new = before.get(field), after.get(field)
        if old == new:
            continue
        change = {"before": old, "after": new}
        if isinstance(old, str) and isinstance(new, str):
            change["diff"] = "\n".join(
                unified_diff(
                    old.splitlines(),
                    new.splitlines(),
                    fromfile="before",
                    tofile="after",
                    lineterm="",
                )
            )
        result[field] = change
    return result


@lru_cache(maxsize=1)
def pipeline_code_hash() -> str:
    root = Path(__file__).parent / "ai"
    return stable_hash(
        {name: (root / name).read_text() for name in ("backends.py", "content_processor.py")}
    )


@lru_cache(maxsize=1)
def policy_code_hash() -> str:
    root = Path(__file__).parent
    return stable_hash(
        {
            name: (root / name).read_text()
            for name in ("editorial_learning.py", "editorial.py", "provenance.py")
        }
    )


def version_context() -> dict:
    return {
        "policy_version": POLICY_VERSION,
        "pipeline_code_hash": pipeline_code_hash(),
        "policy_code_hash": policy_code_hash(),
        "translation_model": settings.llm_translation_model,
        "polish_model": "claude-sonnet-4-6",
        "analysis_model": settings.claude_model,
        "glossary_version": "not-configured",
    }


def training_eligible(kind: str, actor: dict, reason: str, changes: dict) -> bool:
    if actor.get("kind") != "human" or reason == "capacity":
        return False
    if kind in {"approved", "translation_requested"}:
        return True
    if kind == "edited":
        return bool(changes) and reason not in {"unspecified", "other"}
    return kind == "rejected" and reason not in {"unspecified", "other"}
