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
                
                # Create processed news item with original content and translations
                processed_item = ProcessedNewsItem(
                    id=news_item.id,
                    title=news_item.title,  # Keep original title
                    content=news_item.content,  # Keep original content
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
                    tags=processed_data.get('tags', []),
                    # Translation fields
                    translated_title=translated_title,
                    translated_summary=processed_data.get('summary', ''),
                    translated_key_points=processed_data.get('key_points', []),
                    original_language=self._detect_language(news_item.title)
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
    
    def _is_english(self, text: str) -> bool:
        """Check if text is in English"""
        # Simple heuristic: check for Latin characters vs Cyrillic
        latin_chars = sum(1 for char in text if char.isalpha() and ord(char) < 128)
        cyrillic_chars = sum(1 for char in text if '\u0400' <= char <= '\u04FF')
        total_chars = latin_chars + cyrillic_chars
        
        if total_chars == 0:
            return False
        
        return latin_chars > cyrillic_chars
    
    def _translate_to_russian_simple(self, text: str) -> str:
        """Simple translation fallback for English text"""
        # Simple keyword-based translation for common F1 terms
        translations = {
            "driver": "гонщик",
            "team": "команда",
            "race": "гонка",
            "championship": "чемпионат",
            "points": "очки",
            "overtake": "обгон",
            "position": "позиция",
            "chance": "шанс",
            "risk": "риск",
            "explains": "объясняет",
            "thoughts": "мысли",
            "decision": "решение",
            "recent": "недавний",
            "reveals": "раскрывает",
            "chose": "выбрал",
            "concerns": "опасения",
            "losing": "потеря",
            "personal": "личный",
            "standings": "зачет",
            "prioritized": "приоритизировал",
            "chances": "шансы",
            "winning": "победа",
            "constructors": "конструкторов",
            "significant": "значительный",
            "factor": "фактор"
        }
        
        # Simple word-by-word translation
        words = text.split()
        translated_words = []
        for word in words:
            # Remove punctuation for lookup
            clean_word = word.strip('.,!?;:"()[]{}')
            if clean_word.lower() in translations:
                translated_words.append(translations[clean_word.lower()])
            else:
                translated_words.append(word)
        
        return " ".join(translated_words)
    
    def process_russian_news_fast(self, news_item: NewsItem) -> Dict[str, Any]:
        """Fast processing for Russian news without Ollama"""
        logger.info(f"Fast processing Russian news: {news_item.title[:50]}...")
        
        # Extract basic tags from title and content
        tags = self._extract_tags_fast(news_item.title, news_item.content)
        
        # Calculate relevance score based on F1 keywords
        relevance_score = self._calculate_relevance_fast(news_item.title, news_item.content)
        
        # Basic importance assessment (1-3)
        importance_level = self._calculate_importance_fast(news_item.title, news_item.content)
        
        # Use first 200-300 characters as summary
        summary = news_item.content[:250] + "..." if len(news_item.content) > 250 else news_item.content
        
        return {
            "summary": summary,
            "key_points": [],  # Empty for Russian news
            "sentiment": "neutral",
            "importance_level": importance_level,
            "formatted_content": news_item.content,  # Use original content
            "tags": tags,
            "relevance_score": relevance_score,
            "translated_title": news_item.title,  # No translation needed
            "translated_content": news_item.content,  # No translation needed
            "translated_summary": summary,  # No translation needed
            "translated_key_points": [],  # Empty for Russian news
            "translated_formatted_content": news_item.content  # No translation needed
        }
    
    def _extract_tags_fast(self, title: str, content: str) -> List[str]:
        """Extract basic tags from title and content"""
        text = f"{title} {content}".lower()
        
        # F1-related keywords
        f1_keywords = [
            "формула 1", "f1", "гонка", "гонщик", "команда", "чемпионат",
            "ферстаппен", "хэмилтон", "норрис", "леклер", "сайнц", "перес",
            "альфатаури", "хаас", "астон мартин", "маклерен", "феррари",
            "ред булл", "мерседес", "альпин", "вильямс", "заубер",
            "квалификация", "гонка", "очки", "подиум", "победа",
            "обгон", "авария", "штраф", "дисквалификация", "дрс"
        ]
        
        tags = []
        for keyword in f1_keywords:
            if keyword in text:
                tags.append(keyword.title())
        
        # Add source-specific tags
        if "telegram" in text or "тг" in text:
            tags.append("Telegram")
        if "rss" in text or "лента" in text:
            tags.append("RSS")
        
        return list(set(tags))[:5]  # Limit to 5 tags
    
    def _calculate_relevance_fast(self, title: str, content: str) -> float:
        """Calculate relevance score based on F1 keywords"""
        text = f"{title} {content}".lower()
        
        # High relevance keywords
        high_relevance = [
            "формула 1", "f1", "гонка", "гонщик", "команда", "чемпионат",
            "квалификация", "очки", "подиум", "победа", "обгон"
        ]
        
        # Medium relevance keywords
        medium_relevance = [
            "авария", "штраф", "дисквалификация", "дрс", "шины", "трасса"
        ]
        
        # Count matches
        high_count = sum(1 for keyword in high_relevance if keyword in text)
        medium_count = sum(1 for keyword in medium_relevance if keyword in text)
        
        # Calculate score (0.0 to 1.0)
        score = (high_count * 0.3) + (medium_count * 0.1)
        return min(score, 1.0)
    
    def _calculate_importance_fast(self, title: str, content: str) -> int:
        """Calculate importance level (1-3) based on content analysis"""
        text = f"{title} {content}".lower()
        
        # High importance indicators
        if any(word in text for word in ["победа", "рекорд", "исторический", "впервые", "сенсация"]):
            return 3
        
        # Medium importance indicators
        if any(word in text for word in ["авария", "штраф", "дисквалификация", "подиум", "очки"]):
            return 2
        
        # Default importance
        return 1
    
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
ТЫ ДОЛЖЕН ОТВЕЧАТЬ ТОЛЬКО НА РУССКОМ ЯЗЫКЕ! НИКАКИХ АНГЛИЙСКИХ СЛОВ!

Проанализируй эту новость о Формуле 1 и создай JSON ответ НА РУССКОМ ЯЗЫКЕ.

Заголовок: {final_title}
Содержание: {final_content}
Источник: {news_item.source}
URL: {news_item.url}

Создай JSON с полями НА РУССКОМ ЯЗЫКЕ:

{{
    "summary": "Краткое изложение на русском языке в 2-3 предложениях",
    "key_points": ["Первый ключевой момент на русском", "Второй ключевой момент на русском", "Третий ключевой момент на русском"],
    "sentiment": "positive/negative/neutral",
    "importance_level": 1-5,
    "formatted_content": "Отформатированный текст для соцсетей на русском с эмодзи",
    "tags": ["F1", "Русский тег", "Еще тег"]
}}

ВАЖНО: Все текстовые поля должны быть на русском языке!
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
                # Clean up JSON string - remove any trailing commas or invalid characters
                json_str = json_str.rstrip(',')
                parsed_data = json.loads(json_str)
                
                # Force Russian language for text fields
                if 'summary' in parsed_data and isinstance(parsed_data['summary'], str):
                    # If summary is in English, translate it
                    if self._is_english(parsed_data['summary']):
                        parsed_data['summary'] = self._translate_to_russian_simple(parsed_data['summary'])
                
                if 'key_points' in parsed_data and isinstance(parsed_data['key_points'], list):
                    # Translate key points if they are in English
                    translated_points = []
                    for point in parsed_data['key_points']:
                        if isinstance(point, str):
                            if self._is_english(point):
                                translated_points.append(self._translate_to_russian_simple(point))
                            else:
                                translated_points.append(point)
                        else:
                            translated_points.append(str(point))
                    parsed_data['key_points'] = translated_points
                
                if 'formatted_content' in parsed_data and isinstance(parsed_data['formatted_content'], str):
                    # Translate formatted content if it's in English
                    if self._is_english(parsed_data['formatted_content']):
                        parsed_data['formatted_content'] = self._translate_to_russian_simple(parsed_data['formatted_content'])
                
                return parsed_data
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
