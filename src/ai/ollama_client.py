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
            
            # Create processing prompt
            prompt = self._create_processing_prompt(news_item)
            
            # Call Ollama API
            response = await self._call_ollama(prompt)
            
            if response:
                # Parse response
                processed_data = self._parse_ollama_response(response)
                
                # Create processed news item
                processed_item = ProcessedNewsItem(
                    **news_item.dict(),
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
    
    def _create_processing_prompt(self, news_item: NewsItem) -> str:
        """Create prompt for Ollama processing"""
        prompt = f"""
Analyze this F1 news article and provide a structured response in JSON format.

Title: {news_item.title}
Content: {news_item.content}
Source: {news_item.source}
URL: {news_item.url}

Please provide the following information in JSON format:

1. summary: A concise 2-3 sentence summary of the article
2. key_points: Array of 3-5 key points from the article
3. sentiment: One of "positive", "negative", or "neutral"
4. importance_level: Integer from 1-5 (1=low, 5=high importance)
5. formatted_content: A well-formatted version for social media with emojis and hashtags
6. tags: Array of relevant tags (e.g., ["F1", "Hamilton", "Mercedes", "Race"])

Focus on F1-specific content and make it engaging for social media.

Response format (JSON only):
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
