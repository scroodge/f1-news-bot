"""
Ollama client for AI processing
"""
import asyncio
import requests
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from ..config import settings
from ..models import NewsItem, ProcessedNewsItem, ProcessingResult

logger = logging.getLogger(__name__)

class OllamaClient:
    """Client for interacting with Ollama API"""
    
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model
        self.session = None
    
    async def initialize(self):
        """Initialize HTTP session"""
        self.session = True  # We use requests, not aiohttp
        logger.info(f"Ollama client initialized with model: {self.model}")
    
    async def close(self):
        """Close HTTP session"""
        self.session = None
    
    async def process_news_item(self, news_item: NewsItem) -> ProcessingResult:
        """Process news item with AI"""
        start_time = datetime.utcnow()
        
        try:
            if not self.session:
                await self.initialize()
            
            # Check if translation is needed
            translated_title, translated_content = await self._translate_if_needed(
                news_item.title, news_item.content
            )
            
            # Create processing prompt with translated content
            prompt = self._create_processing_prompt(news_item, translated_title, translated_content)
            
            # Call Ollama API
            response = await self._call_ollama(prompt)
            
            if response:
                # Parse response
                processed_data = self._parse_ollama_response(response)
                
                # Create processed news item with translated content
                processed_item = ProcessedNewsItem(
                    id=news_item.id,
                    title=translated_title,  # Use translated title
                    content=translated_content,  # Use translated content
                    url=news_item.url,
                    source=news_item.source,
                    source_type=news_item.source_type,
                    published_at=news_item.published_at,
                    relevance_score=news_item.relevance_score,
                    keywords=news_item.keywords,
                    processed=True,
                    published=False,
                    created_at=datetime.utcnow(),
                    summary=processed_data.get('summary', ''),
                    key_points=processed_data.get('key_points', []),
                    sentiment=processed_data.get('sentiment', 'neutral'),
                    importance_level=processed_data.get('importance_level', 1),
                    formatted_content=processed_data.get('formatted_content', ''),
                    tags=processed_data.get('tags', [])
                )
                
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                
                return ProcessingResult(
                    success=True,
                    news_item=processed_item,
                    processing_time=processing_time
                )
            else:
                return ProcessingResult(
                    success=False,
                    error_message="Failed to get response from Ollama"
                )
                
        except Exception as e:
            logger.error(f"Error processing news item with Ollama: {e}")
            return ProcessingResult(
                success=False,
                error_message=str(e)
            )
    
    def _detect_language(self, text: str) -> str:
        """Detect if text is in Russian or other language"""
        # Simple heuristic: check for Cyrillic characters
        cyrillic_chars = sum(1 for char in text if '\u0400' <= char <= '\u04FF')
        total_chars = len([char for char in text if char.isalpha()])
        
        if total_chars == 0:
            return "unknown"
        
        cyrillic_ratio = cyrillic_chars / total_chars
        return "russian" if cyrillic_ratio > 0.3 else "other"
    
    async def _translate_if_needed(self, title: str, content: str) -> tuple:
        """Translate title and content to Russian if needed"""
        # Check if title is in Russian
        title_lang = self._detect_language(title)
        content_lang = self._detect_language(content)
        
        logger.info(f"Language detection - Title: {title_lang}, Content: {content_lang}")
        
        translated_title = title
        translated_content = content
        
        # Translate title if not Russian
        if title_lang != "russian":
            logger.info(f"Translating title from {title_lang} to Russian")
            translated_title = await self._translate_text(title)
            logger.info(f"Title translation result: {translated_title[:50]}...")
        else:
            logger.info("Title is already in Russian, skipping translation")
        
        # Translate content if not Russian
        if content_lang != "russian":
            logger.info(f"Translating content from {content_lang} to Russian")
            translated_content = await self._translate_text(content)
            logger.info(f"Content translation result: {translated_content[:50]}...")
        else:
            logger.info("Content is already in Russian, skipping translation")
        
        return translated_title, translated_content
    
    async def _translate_text(self, text: str) -> str:
        """Translate text to Russian using Ollama"""
        try:
            prompt = f"""Переведи следующий текст на русский язык. Сохрани структуру и форматирование. Если текст уже на русском, верни его без изменений.

Текст для перевода:
{text}

Перевод:"""
            
            logger.info(f"Translating text: {text[:50]}...")
            response = await self._call_ollama(prompt)
            logger.info(f"Translation response: {response}")
            
            if response:
                translated = response.strip()
                logger.info(f"Translated result: {translated}")
                return translated
            else:
                logger.warning("No translation response received, returning original text")
                return text
            
        except Exception as e:
            logger.error(f"Error translating text: {e}")
            return text  # Return original text if translation fails
    
    def _create_processing_prompt(self, news_item: NewsItem, title: str = None, content: str = None) -> str:
        """Create prompt for Ollama processing"""
        # Use translated content if provided, otherwise use original
        final_title = title if title else news_item.title
        final_content = content if content else news_item.content
        
        prompt = f"""
Проанализируй эту новость о Формуле 1 и предоставь структурированный ответ в формате JSON.

Заголовок: {final_title}
Содержание: {final_content}
Источник: {news_item.source}
URL: {news_item.url}

Пожалуйста, предоставь следующую информацию в формате JSON:

1. summary: Краткое изложение статьи в 2-3 предложениях
2. key_points: Массив из 3-5 ключевых моментов статьи
3. sentiment: Одно из "positive", "negative", или "neutral"
4. importance_level: Целое число от 1-5 (1=низкая, 5=высокая важность)
5. formatted_content: Хорошо отформатированная версия для социальных сетей с эмодзи и хештегами
6. tags: Массив релевантных тегов (например, ["F1", "Хэмилтон", "Мерседес", "Гонка"])

Сосредоточься на контенте, связанном с F1, и сделай его привлекательным для социальных сетей.

Формат ответа (только JSON):
{{
    "summary": "...",
    "key_points": ["...", "..."],
    "sentiment": "...",
    "importance_level": ...,
    "formatted_content": "...",
    "tags": ["...", "..."]
}}
"""
        return prompt
    
    async def _call_ollama(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Call Ollama API"""
        try:
            url = f"{self.base_url}/api/generate"
            
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "max_tokens": 1000
                }
            }
            
            response = requests.post(url, json=payload, timeout=60)
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '')
            else:
                logger.error(f"Ollama API returned status {response.status_code}")
                return None
                    
        except requests.exceptions.Timeout:
            logger.error("Timeout calling Ollama API")
            return None
        except Exception as e:
            logger.error(f"Error calling Ollama API: {e}")
            return None
    
    def _parse_ollama_response(self, response: str) -> Dict[str, Any]:
        """Parse Ollama response"""
        try:
            # Try to extract JSON from response
            response = response.strip()
            
            # Find JSON in response
            start_idx = response.find('{')
            end_idx = response.rfind('}') + 1
            
            if start_idx != -1 and end_idx != 0:
                json_str = response[start_idx:end_idx]
                return json.loads(json_str)
            else:
                # Fallback: create basic response
                return {
                    "summary": response[:200] + "..." if len(response) > 200 else response,
                    "key_points": [],
                    "sentiment": "neutral",
                    "importance_level": 1,
                    "formatted_content": response,
                    "tags": []
                }
                
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing Ollama response: {e}")
            # Fallback response
            return {
                "summary": response[:200] + "..." if len(response) > 200 else response,
                "key_points": [],
                "sentiment": "neutral",
                "importance_level": 1,
                "formatted_content": response,
                "tags": []
            }
    
    async def check_health(self) -> bool:
        """Check if Ollama is healthy"""
        try:
            url = f"{self.base_url}/api/tags"
            response = requests.get(url, timeout=10)
            return response.status_code == 200
                
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False
    
    async def get_available_models(self) -> List[str]:
        """Get list of available models"""
        try:
            url = f"{self.base_url}/api/tags"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return [model['name'] for model in data.get('models', [])]
            return []
                
        except Exception as e:
            logger.error(f"Error getting available models: {e}")
            return []
