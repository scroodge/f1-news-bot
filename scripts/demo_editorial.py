"""Local editorial demo with in-memory SQLite and simulated AI/source retrieval.

Run: uv run python scripts/demo_editorial.py
Nothing is fetched, published or written to the production database.
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

import src.webapp.router as web
from src.collectors.web_scraper import WebScraperCollector
from src.database import DatabaseManager
from src.models import NewsItem, ProcessedNewsItem, SourceType
from src.webapp.auth import require_admin

ORIGINAL_URL = "https://www.the-race.com/formula-1/demo-ferrari-technical-interview/"
db = DatabaseManager("sqlite+aiosqlite://")


def article(title, url, source, text, quality="article", story="demo-upgrade", references=None):
    return NewsItem(
        title="[DEMO] " + title,
        url=url,
        source=source,
        content=text,
        source_type=SourceType.WEB,
        published_at=datetime.utcnow(),
        relevance_score=0.95,
        story_id=story,
        collection_info={
            "text_quality": quality,
            "text_origin": "demo",
            "references": references or [],
        },
    )


FULL_TEXT = (
    "DEMO: This is a fictional article for interface testing, not actual Formula 1 news.\n\n"
    "Speaking exclusively in this demonstration, an engineer explains how a front wing "
    "could change airflow around the car. The example contrasts an original technical "
    "interview with secondary coverage of the same topic. No real statement is attributed "
    "to a driver, team or publication.\n\n"
    "The additional report includes a different observation, so both articles remain "
    "available inside the story. Moderators can inspect each text and select what to translate.\n\n"
) * 2


class DemoProcessor:
    def __init__(self):
        self.progress = {}

    async def translate_news(self, item_id):
        self.progress[item_id] = SimpleNamespace(
            step="translating",
            detail="",
            chunk_current=0,
            chunk_total=1,
            finished=False,
            success=False,
            error=None,
        )
        await asyncio.sleep(1)
        item = await db.get_item(item_id)
        translated = ProcessedNewsItem(
            **item.model_dump(),
            summary="Дэманстрацыйны тэкст.",
            translated_title="[ДЭМА] Прыклад перакладу матэрыялу",
            translated_summary="Гэта імітацыя перакладу для праверкі інтэрфейсу. "
            "Сапраўдная мадэль AI не выклікалася.\n\n" + item.content,
            original_language="en",
        )
        await db.mark_processed(item_id, translated)
        self.progress[item_id] = SimpleNamespace(
            step="done",
            detail="",
            chunk_current=1,
            chunk_total=1,
            finished=True,
            success=True,
            error=None,
        )
        return True

    def get_progress(self, item_id):
        return self.progress.get(item_id)

    async def generate_keypoints(self, item_id):
        return await db.update_fields(
            item_id,
            key_points=[
                "Дэманстрацыйны пункт: праверка інтэрфейсу.",
                "AI і публікацыя ў Telegram адключаныя.",
            ],
        )


async def demo_reference(self, url):
    if url != ORIGINAL_URL:
        return None
    return article(
        "Original technical interview", url, "The Race · DEMO", FULL_TEXT, story="demo-attribution"
    )


@asynccontextmanager
async def lifespan(app):
    await db.create_tables()  # Disposable in-memory test DB only.
    web.db_manager = db
    web._content_processor = DemoProcessor()
    WebScraperCollector.fetch_reference = demo_reference
    await db.save_news_item(
        article(
            "Ferrari front-wing analysis: original interview",
            "https://www.autosport.com/f1/news/demo-original-front-wing/123456/",
            "Autosport · DEMO",
            FULL_TEXT,
        )
    )
    await db.save_news_item(
        article(
            "Another report on the same Ferrari upgrade",
            "https://www.planetf1.com/news/demo-front-wing-report",
            "PlanetF1 · DEMO",
            "DEMO: According to reports, the same upgrade may affect balance. "
            "This article includes extra details and remains separately editable.\n\n" + FULL_TEXT,
            references=[
                {
                    "url": "https://www.autosport.com/f1/news/demo-original-front-wing/123456/",
                    "source": "autosport.com",
                    "kind": "attribution",
                    "evidence": "DEMO: As reported by Autosport, an engineer discussed the wing.",
                }
            ],
        )
    )
    await db.save_news_item(
        article(
            "Only a teaser is available",
            "https://www.motorsport.com/f1/news/demo-short-news/123456/",
            "Motorsport · DEMO",
            "DEMO: A short RSS teaser. The full article could not be retrieved. "
            "Try translation to see the confirmation before it starts.",
            quality="teaser",
            story="demo-teaser",
        )
    )
    await db.save_news_item(
        article(
            "Report citing an original that has not been collected",
            "https://racingnews365.com/demo-reported-technical-interview",
            "RacingNews365 · DEMO",
            "DEMO: According to The Race, an engineer explains the aerodynamic changes. "
            "Use “Атрымаць артыкул” to add the simulated original to this story.",
            quality="short",
            story="demo-attribution",
            references=[
                {
                    "url": ORIGINAL_URL,
                    "source": "the-race.com",
                    "kind": "attribution",
                    "evidence": "DEMO: According to The Race, the interview explains the technical changes.",
                }
            ],
        )
    )
    await db.save_news_item(
        article(
            "Subscriber article: available text only",
            "https://www.autosport.com/f1/news/demo-subscriber-analysis/654321/",
            "Autosport · DEMO",
            "DEMO: Subscribe to continue reading. Only this excerpt is available.",
            quality="paywall",
            story="demo-paywall",
        )
    )
    yield
    await db.close()


app = FastAPI(lifespan=lifespan)
app.dependency_overrides[require_admin] = lambda: {"id": 0, "first_name": "Demo"}


@app.get("/admin", response_class=HTMLResponse)
async def demo_page():
    html = (web.STATIC_DIR / "index.html").read_text()
    html = html.replace('<script src="https://telegram.org/js/telegram-web-app.js"></script>', "")
    banner = """<div role="note" style="padding:12px 16px;background:#f7dc6f;color:#222;text-align:center">
    <b>ДЭМА · Тэставыя навіны</b><br>AI і загрузка крыніц імітуюцца.
    Нічога не публікуецца. Перазапуск аднаўляе прыклады.</div>"""
    return html.replace("<body>", "<body>" + banner)


app.include_router(web.api)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=18080)
