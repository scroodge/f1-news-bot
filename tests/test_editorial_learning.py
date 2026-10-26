"""Feedback provenance, atomic snapshots and strictly non-executing shadow rules."""

from datetime import datetime

import pytest
from sqlalchemy import func, select

import src.database as database_module
from src.database import DatabaseManager, EditorialEventDB
from src.editorial_learning import shadow_recommendation
from src.models import NewsItem, NewsStatus, ProcessedNewsItem, SourceType

HUMAN = {"kind": "human", "id": "7", "interface": "miniapp"}


def article(url="https://www.autosport.com/f1/news/new-ferrari-upgrade/12345/"):
    return NewsItem(
        title="Ferrari reveals new front wing",
        content="F1 technical analysis " * 80,
        url=url,
        source="Autosport",
        source_type=SourceType.WEB,
        published_at=datetime.utcnow(),
        relevance_score=0.9,
        collection_info={"text_quality": "article"},
    )


@pytest.fixture
async def db():
    manager = DatabaseManager("sqlite+aiosqlite://")
    await manager.create_tables()
    yield manager
    await manager.close()


async def draft(db, item_id):
    original = await db.get_item(item_id)
    await db.mark_processed(
        item_id,
        ProcessedNewsItem(
            **original.model_dump(),
            summary="Каротка",
            translated_title="Навіна",
            translated_summary="Пілот можа перайсці.",
        ),
    )


def test_shadow_is_only_a_suggestion_and_incomplete_or_rumored_sources_abstain():
    original = article()
    result = shadow_recommendation(original)
    assert result["selection"] == "translate"
    assert result["publication"] == "human_review"
    assert result["automatic_actions"] is False
    assert original.status == NewsStatus.COLLECTED
    original.content = "An unconfirmed rumour about Ferrari"
    assert shadow_recommendation(original)["selection"] == "human_review"
    original.collection_info = {"text_quality": "teaser"}
    assert shadow_recommendation(original)["selection"] == "human_review"


async def test_source_drafts_and_human_corrections_are_retained(db):
    item_id = await db.save_news_item(article())
    await draft(db, item_id)
    await db.update_fields(
        item_id,
        translated_summary="Пілот перайшоў.",
        editorial_actor=HUMAN,
        feedback_reason="translation_error",
        feedback_note="Зменена мадальнасць",
    )
    assert await db.approve(item_id, actor=HUMAN, reason_code="interesting")
    events = list(reversed(await db.get_editorial_history(item_id)))
    assert [e["kind"] for e in events] == ["collected", "draft_generated", "edited", "approved"]
    assert events[0]["after"]["content"] == article().content
    edit = events[2]
    assert edit["before"]["translated_summary"] == "Пілот можа перайсці."
    assert edit["after"]["translated_summary"] == "Пілот перайшоў."
    assert "diff" in edit["changes"]["translated_summary"]
    assert edit["reason_code"] == "translation_error"
    assert edit["training_eligible"] is True
    assert edit["actor"]["id"] == "7"
    assert edit["versions"]["pipeline_code_hash"]
    assert edit["recommendation"]["publication"] == "human_review"
    assert events[1]["training_eligible"] is False
    assert events[1]["source_hash"] == edit["source_hash"]
    assert events[1]["draft_hash"] != edit["draft_hash"]
    assert not await db.approve(item_id, actor=HUMAN)
    assert len(await db.get_editorial_history(item_id)) == 4


async def test_failed_journal_write_rolls_back_the_edit(db, monkeypatch):
    item_id = await db.save_news_item(article())
    await draft(db, item_id)

    def fail(*args, **kwargs):
        raise RuntimeError("simulated journal failure")

    monkeypatch.setattr(database_module, "_append_editorial_event", fail)
    with pytest.raises(RuntimeError):
        await db.update_fields(
            item_id, translated_summary="Must not persist", editorial_actor=HUMAN
        )
    assert (await db.get_item(item_id)).translated_summary == "Пілот можа перайсці."
    assert len(await db.get_editorial_history(item_id)) == 2


async def test_bulk_system_demo_and_capacity_events_are_not_training_labels(db):
    bulk_id = await db.save_news_item(article())
    assert await db.reject_all_collected(actor=HUMAN) == 1
    assert not (await db.get_editorial_history(bulk_id))[0]["training_eligible"]
    for i, actor in enumerate([None, {"kind": "demo"}, HUMAN]):
        item_id = await db.save_news_item(article(f"https://example.com/{i}"))
        await db.reject(
            item_id, actor=actor, reason_code="capacity" if actor == HUMAN else "duplicate"
        )
        assert not (await db.get_editorial_history(item_id))[0]["training_eligible"]
    assert (await db.get_editorial_summary())["eligible_events"] == 0


async def test_duplicate_ingestion_and_noop_edit_do_not_create_extra_events(db):
    item_id = await db.save_news_item(article())
    assert await db.save_news_item(article()) is None
    await draft(db, item_id)
    await db.update_fields(
        item_id, translated_summary="Пілот можа перайсці.", editorial_actor=HUMAN
    )
    assert len(await db.get_editorial_history(item_id)) == 2
    # Ordinary news deletion does not cascade into the immutable audit snapshots.
    await db.delete_item(item_id)
    async with db.session() as session:
        assert await session.scalar(select(func.count()).select_from(EditorialEventDB)) == 2


async def test_late_ai_result_cannot_undo_human_rejection(db):
    item_id = await db.save_news_item(article())
    original = await db.get_item(item_id)
    await db.reject(item_id, actor=HUMAN, reason_code="unverified")
    stale = ProcessedNewsItem(**original.model_dump(), summary="Too late")
    assert not await db.mark_processed(item_id, stale)
    assert (await db.get_item(item_id)).status == NewsStatus.REJECTED
    assert [e["kind"] for e in await db.get_editorial_history(item_id)] == ["rejected", "collected"]


async def test_baseline_comparison_uses_predecision_snapshot_and_excludes_demo(db):
    first = await db.save_news_item(article())
    await db.record_editorial_action(first, "translation_requested", actor=HUMAN)
    second = await db.save_news_item(
        article("https://www.autosport.com/f1/news/other-upgrade/12345/")
    )
    await db.reject(second, actor=HUMAN, reason_code="not_interesting")
    demonstration = article("https://example.com/demo")
    demonstration.collection_info["text_origin"] = "demo"
    demo_id = await db.save_news_item(demonstration)
    await db.record_editorial_action(demo_id, "translation_requested", actor=HUMAN)
    summary = await db.get_editorial_summary()
    assert summary["eligible_events"] == 2
    assert summary["selection_baseline"] == {"comparable": 2, "matches": 1, "deferred": 0}
    latest = (await db.get_editorial_history(second))[0]
    assert latest["before"]["status"] == "collected"
    assert latest["after"]["status"] == "rejected"
    assert latest["recommendation"]["selection"] == "translate"
    assert not (await db.get_editorial_history(demo_id))[0]["training_eligible"]
