"""
Content processor for AI-powered news analysis
"""
import asyncio
from typing import List, Optional
from datetime import datetime
import logging

from .ollama_client import OllamaClient
from ..models import NewsItem, ProcessedNewsItem, ProcessingResult
from ..database import db_manager
from ..services.redis_service import redis_service

logger = logging.getLogger(__name__)

class ContentProcessor:
    """AI-powered content processor"""
    
    def __init__(self):
        self.ollama_client = OllamaClient()
        self.processing_queue = []
        self.is_processing = False
    
    async def initialize(self):
        """Initialize the processor"""
        await self.ollama_client.initialize()
        
        # Check Ollama health
        if not await self.ollama_client.check_health():
            logger.error("Ollama is not available")
            return False
        
        logger.info("Content processor initialized successfully")
        return True
    
    def _detect_language(self, text: str) -> str:
        """Detect if text is in Russian or other language"""
        # Simple heuristic: check for Cyrillic characters
        cyrillic_chars = sum(1 for char in text if '\u0400' <= char <= '\u04FF')
        total_chars = len([char for char in text if char.isalpha()])
        
        if total_chars == 0:
            return "unknown"
        
        cyrillic_ratio = cyrillic_chars / total_chars
        return "russian" if cyrillic_ratio > 0.3 else "other"
    
    async def _translate_to_russian(self, text: str) -> str:
        """Translate text to Russian using Ollama"""
        try:
            prompt = f"""Переведи следующий текст на русский язык. Сохрани структуру и форматирование. Если текст уже на русском, верни его без изменений.

Текст для перевода:
{text}

Перевод:"""
            
            response = await self.ollama_client.generate_response(prompt)
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error translating text: {e}")
            return text  # Return original text if translation fails
    
    async def process_news_batch(self, news_items: List[NewsItem]) -> List[ProcessingResult]:
        """Process a batch of news items"""
        results = []
        
        for news_item in news_items:
            try:
                result = await self.process_single_news(news_item)
                results.append(result)
                
                # Small delay to avoid overwhelming Ollama
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error processing news item {news_item.id}: {e}")
                results.append(ProcessingResult(
                    success=False,
                    error_message=str(e)
                ))
        
        return results
    
    async def process_single_news(self, news_item: NewsItem) -> ProcessingResult:
        """Process a single news item"""
        try:
            # Check if news is in Russian
            title_lang = self._detect_language(news_item.title)
            content_lang = self._detect_language(news_item.content)
            
            if title_lang == "russian" and content_lang == "russian":
                # Fast processing for Russian news (skip Ollama)
                logger.info(f"Fast processing Russian news: {news_item.title[:50]}...")
                result = self._process_russian_news_fast(news_item)
            else:
                # Full processing with Ollama for non-Russian news
                logger.info(f"Full processing with Ollama: {news_item.title[:50]}...")
                result = await self.ollama_client.process_news_item(news_item)
            
            if result.success and result.news_item:
                # Save processed item to database
                await db_manager.update_processed_news(
                    news_item.id, 
                    result.news_item
                )
                
                # Add to Redis moderation queue for Telegram bot
                await redis_service.add_news_to_moderation_queue(result.news_item)
                
                logger.info(f"Successfully processed news item: {news_item.title[:50]}...")
            else:
                logger.error(f"Failed to process news item: {result.error_message}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing news item: {e}")
            return ProcessingResult(
                success=False,
                error_message=str(e)
            )
    
    def _process_russian_news_fast(self, news_item: NewsItem) -> ProcessingResult:
        """Fast processing for Russian news without Ollama"""
        try:
            # Use OllamaClient's fast processing method
            processed_data = self.ollama_client.process_russian_news_fast(news_item)
            
            # Create ProcessedNewsItem
            processed_news = ProcessedNewsItem(
                id=news_item.id,
                title=news_item.title,
                content=news_item.content,
                url=news_item.url,
                source=news_item.source,
                source_type=news_item.source_type,
                published_at=news_item.published_at,
                created_at=news_item.created_at,
                summary=processed_data["summary"],
                key_points=processed_data["key_points"],
                sentiment=processed_data["sentiment"],
                importance_level=processed_data["importance_level"],
                formatted_content=processed_data["formatted_content"],
                tags=processed_data["tags"],
                relevance_score=processed_data["relevance_score"],
                translated_title=processed_data["translated_title"],
                translated_content=processed_data["translated_content"],
                translated_summary=processed_data["translated_summary"],
                translated_key_points=processed_data["translated_key_points"],
                translated_formatted_content=processed_data["translated_formatted_content"],
                image_url=news_item.image_url,
                video_url=news_item.video_url,
                processed_at=datetime.now()
            )
            
            return ProcessingResult(
                success=True,
                news_item=processed_news
            )
            
        except Exception as e:
            logger.error(f"Error in fast processing: {e}")
            return ProcessingResult(
                success=False,
                error_message=str(e)
            )
    
    async def process_pending_news(self, limit: int = 10) -> List[ProcessingResult]:
        """Process pending news items from database"""
        try:
            # Get unprocessed news items
            pending_news = await db_manager.get_unprocessed_news(limit)
            
            if not pending_news:
                logger.info("No pending news items to process")
                return []
            
            logger.info(f"Processing {len(pending_news)} pending news items")
            
            # Process the batch
            results = await self.process_news_batch(pending_news)
            
            # Log results
            successful = sum(1 for r in results if r.success)
            failed = len(results) - successful
            
            logger.info(f"Processing completed: {successful} successful, {failed} failed")
            
            return results
            
        except Exception as e:
            logger.error(f"Error processing pending news: {e}")
            return []
    
    async def get_processing_stats(self) -> dict:
        """Get processing statistics"""
        try:
            stats = await db_manager.get_stats()
            
            return {
                "total_collected": stats.total_news_collected,
                "total_processed": stats.total_news_processed,
                "pending_processing": stats.total_news_collected - stats.total_news_processed,
                "processing_rate": stats.total_news_processed / max(stats.total_news_collected, 1),
                "last_processing_time": stats.last_processing_time
            }
            
        except Exception as e:
            logger.error(f"Error getting processing stats: {e}")
            return {}
    
    async def close(self):
        """Close the processor"""
        await self.ollama_client.close()
        logger.info("Content processor closed")
