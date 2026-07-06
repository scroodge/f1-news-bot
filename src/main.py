"""
Main application entry point for F1 News Bot.

Runs the collection + AI-processing loops and exposes the HTTP API.
Moderation and publication happen in the separate Telegram bot process,
reading the same PostgreSQL database.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .ai.content_processor import ContentProcessor
from .collectors.news_collector import NewsCollector
from .config import settings
from .database import db_manager
from .models import NewsStatus
from .utils.logger import setup_logging
from .utils.monitor import system_monitor
from .webapp.router import api as admin_api
from .webapp.router import router as admin_router

logger = setup_logging()


class F1NewsBotApp:
    """Main application class"""

    def __init__(self):
        self.app = FastAPI(
            title="F1 News Bot API",
            description="API for F1 news collection and AI processing",
            version="2.0.0",
        )

        self.news_collector = NewsCollector()
        self.content_processor = ContentProcessor()

        self.collection_task: asyncio.Task | None = None
        self.processing_task: asyncio.Task | None = None
        self.monitoring_task: asyncio.Task | None = None

        self._setup_routes()
        self._setup_middleware()

        # Telegram Mini App admin panel (static page + authenticated API)
        self.app.include_router(admin_router)
        self.app.include_router(admin_api)

    def _setup_routes(self):
        """Setup API routes"""

        @self.app.get("/")
        async def root():
            return {"message": "F1 News Bot API", "status": "running"}

        @self.app.get("/health")
        async def health_check():
            try:
                return await system_monitor.check_system_health()
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                raise HTTPException(status_code=500, detail="Health check failed") from e

        @self.app.post("/api/collect-news")
        async def collect_news(background_tasks: BackgroundTasks):
            """Trigger news collection"""
            background_tasks.add_task(self._collect_news_background)
            return {"status": "success", "message": "News collection started"}

        @self.app.post("/api/process-news")
        async def process_news(background_tasks: BackgroundTasks):
            """Trigger news processing"""
            background_tasks.add_task(self._process_news_background)
            return {"status": "success", "message": "News processing started"}

        @self.app.get("/api/stats")
        async def get_stats():
            """Get system statistics"""
            try:
                stats = await db_manager.get_stats()
                return {
                    "stats": stats.model_dump(),
                    "collection": await self.news_collector.get_collection_stats(),
                    "uptime": system_monitor.get_uptime_stats(),
                }
            except Exception as e:
                logger.error(f"Error getting stats: {e}")
                raise HTTPException(status_code=500, detail=str(e)) from e

        @self.app.get("/api/news")
        async def get_news(status: NewsStatus | None = None, limit: int = 20, offset: int = 0):
            """Get news items, optionally filtered by lifecycle status"""
            try:
                if status is not None:
                    items = await db_manager.get_by_status(status, limit=limit, offset=offset)
                else:
                    # No filter: newest first across all statuses
                    items = []
                    for st in NewsStatus:
                        items.extend(await db_manager.get_by_status(st, limit=limit))
                    items.sort(key=lambda i: i.created_at, reverse=True)
                    items = items[offset : offset + limit]

                return {
                    "news_items": [item.model_dump() for item in items],
                    "count": len(items),
                    "limit": limit,
                    "offset": offset,
                }
            except Exception as e:
                logger.error(f"Error getting news: {e}")
                raise HTTPException(status_code=500, detail=str(e)) from e

    def _setup_middleware(self):
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    async def _collect_news_background(self):
        try:
            logger.info("Starting news collection...")
            news_items = await self.news_collector.collect_all_news()
            logger.info(f"Collected {len(news_items)} news items")
        except Exception as e:
            logger.error(f"Error in news collection: {e}")

    async def _process_news_background(self):
        try:
            logger.info("Starting news processing...")
            results = await self.content_processor.process_pending_news()
            logger.info(f"Processed {len(results)} news items")
        except Exception as e:
            logger.error(f"Error in news processing: {e}")

    async def start_background_tasks(self):
        """Start background loops"""
        if not await db_manager.ping():
            raise RuntimeError(
                "Database unreachable — check DATABASE_URL (and the SSH tunnel in local dev)"
            )
        await self.content_processor.initialize()

        self.collection_task = asyncio.create_task(self._collection_loop())
        self.processing_task = asyncio.create_task(self._processing_loop())
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())

        logger.info("Background tasks started")

    async def _collection_loop(self):
        while True:
            try:
                await self._collect_news_background()
                await asyncio.sleep(settings.check_interval_minutes * 60)
            except Exception as e:
                logger.error(f"Error in collection loop: {e}")
                await asyncio.sleep(60)

    async def _processing_loop(self):
        while True:
            try:
                await self._process_news_background()
                await asyncio.sleep(300)  # every 5 minutes
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                await asyncio.sleep(60)

    async def _monitoring_loop(self):
        while True:
            try:
                await system_monitor.check_system_health()
                await asyncio.sleep(300)  # every 5 minutes
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)

    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Starting graceful shutdown...")

        tasks = [self.collection_task, self.processing_task, self.monitoring_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
        await asyncio.gather(*(t for t in tasks if t), return_exceptions=True)

        await self.content_processor.close()
        await self.news_collector.close()
        await db_manager.close()

        logger.info("Shutdown complete")


# Create app instance
app_instance = F1NewsBotApp()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    await app_instance.start_background_tasks()
    yield
    await app_instance.shutdown()


app_instance.app.router.lifespan_context = lifespan

# Export FastAPI app
app = app_instance.app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
