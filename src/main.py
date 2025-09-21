"""
Main application entry point for F1 News Bot
"""
import asyncio
import signal
import sys
from typing import Optional
from datetime import datetime
import logging

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config import settings
from .utils.logger import setup_logging, get_logger
from .database import db_manager
from .collectors.news_collector import NewsCollector
from .ai.content_processor import ContentProcessor
from .moderator.content_moderator import ContentModerator
from .moderator.publication_scheduler import PublicationScheduler
from .telegram_bot.bot import F1NewsBot
from .utils.monitor import system_monitor

# Setup logging
logger = setup_logging()

class F1NewsBotApp:
    """Main application class"""
    
    def __init__(self):
        self.app = FastAPI(
            title="F1 News Bot API",
            description="API for F1 news collection, processing, and publication",
            version="1.0.0"
        )
        
        # Initialize components
        self.news_collector = NewsCollector()
        self.content_processor = ContentProcessor()
        self.content_moderator = ContentModerator()
        self.publication_scheduler = PublicationScheduler()
        self.telegram_bot = F1NewsBot()
        
        # Background tasks
        self.collection_task: Optional[asyncio.Task] = None
        self.processing_task: Optional[asyncio.Task] = None
        self.publication_task: Optional[asyncio.Task] = None
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Setup API routes
        self._setup_routes()
        self._setup_middleware()
        
        # Setup signal handlers
        self._setup_signal_handlers()
    
    def _setup_routes(self):
        """Setup API routes"""
        
        @self.app.get("/")
        async def root():
            return {"message": "F1 News Bot API", "status": "running"}
        
        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            try:
                health = await system_monitor.check_system_health()
                return health
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                raise HTTPException(status_code=500, detail="Health check failed")
        
        @self.app.post("/api/collect-news")
        async def collect_news(background_tasks: BackgroundTasks):
            """Trigger news collection"""
            try:
                background_tasks.add_task(self._collect_news_background)
                return {"status": "success", "message": "News collection started"}
            except Exception as e:
                logger.error(f"Error starting news collection: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/process-news")
        async def process_news(background_tasks: BackgroundTasks):
            """Trigger news processing"""
            try:
                background_tasks.add_task(self._process_news_background)
                return {"status": "success", "message": "News processing started"}
            except Exception as e:
                logger.error(f"Error starting news processing: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/moderate-news")
        async def moderate_news(background_tasks: BackgroundTasks):
            """Trigger news moderation"""
            try:
                background_tasks.add_task(self._moderate_news_background)
                return {"status": "success", "message": "News moderation started"}
            except Exception as e:
                logger.error(f"Error starting news moderation: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/schedule-publication")
        async def schedule_publication(background_tasks: BackgroundTasks):
            """Trigger publication scheduling"""
            try:
                background_tasks.add_task(self._schedule_publication_background)
                return {"status": "success", "message": "Publication scheduling started"}
            except Exception as e:
                logger.error(f"Error starting publication scheduling: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/stats")
        async def get_stats():
            """Get system statistics"""
            try:
                stats = await db_manager.get_stats()
                processing_stats = await self.content_processor.get_processing_stats()
                queue_status = self.publication_scheduler.get_queue_status()
                
                return {
                    "database_stats": stats.dict(),
                    "processing_stats": processing_stats,
                    "queue_status": queue_status,
                    "uptime": system_monitor.get_uptime_stats()
                }
            except Exception as e:
                logger.error(f"Error getting stats: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/news")
        async def get_news(limit: int = 20, offset: int = 0, processed: bool = None):
            """Get collected news items"""
            try:
                from .database import db_manager
                from .models import NewsItem, SourceType
                
                with db_manager.get_session() as session:
                    query = session.query(db_manager.NewsItemDB)
                    
                    if processed is not None:
                        query = query.filter(db_manager.NewsItemDB.processed == processed)
                    
                    # Order by creation time (newest first)
                    query = query.order_by(db_manager.NewsItemDB.created_at.desc())
                    
                    # Apply pagination
                    query = query.offset(offset).limit(limit)
                    
                    db_items = query.all()
                    
                    news_items = []
                    for item in db_items:
                        news_item = NewsItem(
                            id=str(item.id),
                            title=item.title,
                            content=item.content,
                            url=item.url,
                            source=item.source,
                            source_type=SourceType(item.source_type),
                            published_at=item.published_at,
                            relevance_score=item.relevance_score,
                            keywords=item.keywords or [],
                            processed=item.processed,
                            published=item.published,
                            created_at=item.created_at
                        )
                        news_items.append(news_item)
                    
                    return {
                        "news_items": [item.dict() for item in news_items],
                        "total_count": len(news_items),
                        "limit": limit,
                        "offset": offset
                    }
            except Exception as e:
                logger.error(f"Error getting news: {e}")
                raise HTTPException(status_code=500, detail=str(e))
    
    def _setup_middleware(self):
        """Setup middleware"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def _collect_news_background(self):
        """Background task for news collection"""
        try:
            logger.info("Starting news collection...")
            news_items = await self.news_collector.collect_all_news()
            logger.info(f"Collected {len(news_items)} news items")
        except Exception as e:
            logger.error(f"Error in news collection: {e}")
    
    async def _process_news_background(self):
        """Background task for news processing"""
        try:
            logger.info("Starting news processing...")
            results = await self.content_processor.process_pending_news()
            logger.info(f"Processed {len(results)} news items")
        except Exception as e:
            logger.error(f"Error in news processing: {e}")
    
    async def _moderate_news_background(self):
        """Background task for news moderation"""
        try:
            logger.info("Starting news moderation...")
            # Get processed news items
            processed_news = await db_manager.get_news_for_publication(limit=10)
            
            for news_item in processed_news:
                moderation_result = self.content_moderator.moderate_news_item(news_item)
                
                if moderation_result['approved']:
                    # Add to publication queue
                    priority = news_item.importance_level
                    self.publication_scheduler.add_to_queue(news_item, priority)
                    logger.info(f"Approved for publication: {news_item.title[:50]}...")
                else:
                    logger.info(f"Rejected: {news_item.title[:50]}... - {moderation_result['reasons']}")
            
        except Exception as e:
            logger.error(f"Error in news moderation: {e}")
    
    async def _schedule_publication_background(self):
        """Background task for publication scheduling"""
        try:
            logger.info("Starting publication scheduling...")
            ready_items = self.publication_scheduler.get_ready_for_publication()
            
            for news_item in ready_items:
                try:
                    result = await self.telegram_bot.publish_to_channel(news_item)
                    
                    if result.success:
                        await db_manager.mark_as_published(news_item.id)
                        self.publication_scheduler.mark_as_published(news_item)
                        logger.info(f"Published: {news_item.title[:50]}...")
                    else:
                        logger.error(f"Publication failed: {result.error_message}")
                        
                except Exception as e:
                    logger.error(f"Error publishing news item: {e}")
            
        except Exception as e:
            logger.error(f"Error in publication scheduling: {e}")
    
    async def start_background_tasks(self):
        """Start background tasks"""
        try:
            # Initialize components
            db_manager.create_tables()  # Remove await - this is a sync function
            await self.content_processor.initialize()
            await self.telegram_bot.initialize()
            
            # Start background tasks
            self.collection_task = asyncio.create_task(self._collection_loop())
            self.processing_task = asyncio.create_task(self._processing_loop())
            self.publication_task = asyncio.create_task(self._publication_loop())
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())
            
            logger.info("Background tasks started")
            
        except Exception as e:
            logger.error(f"Error starting background tasks: {e}")
            raise
    
    async def _collection_loop(self):
        """News collection loop"""
        while True:
            try:
                await self._collect_news_background()
                await asyncio.sleep(settings.check_interval_minutes * 60)
            except Exception as e:
                logger.error(f"Error in collection loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retry
    
    async def _processing_loop(self):
        """News processing loop"""
        while True:
            try:
                await self._process_news_background()
                await asyncio.sleep(300)  # Process every 5 minutes
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                await asyncio.sleep(60)
    
    async def _publication_loop(self):
        """Publication loop"""
        while True:
            try:
                await self._schedule_publication_background()
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in publication loop: {e}")
                await asyncio.sleep(60)
    
    async def _monitoring_loop(self):
        """System monitoring loop"""
        while True:
            try:
                await system_monitor.check_system_health()
                await asyncio.sleep(300)  # Check every 5 minutes
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)
    
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Starting graceful shutdown...")
        
        # Cancel background tasks
        tasks = [self.collection_task, self.processing_task, self.publication_task, self.monitoring_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Close components
        await self.content_processor.close()
        await self.telegram_bot.stop()
        await self.news_collector.close()
        
        logger.info("Shutdown complete")

# Create app instance
app_instance = F1NewsBotApp()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    await app_instance.start_background_tasks()
    yield
    # Shutdown
    await app_instance.shutdown()

# Set lifespan
app_instance.app.router.lifespan_context = lifespan

# Export FastAPI app
app = app_instance.app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
