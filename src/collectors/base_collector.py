"""
Base collector class for all data sources
"""
import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
import re

from ..models import NewsItem, SourceType
from ..config import F1_KEYWORDS

class BaseCollector(ABC):
    """Base class for all news collectors"""
    
    def __init__(self, source_name: str, source_type: SourceType):
        self.source_name = source_name
        self.source_type = source_type
        self.last_check = None
    
    @abstractmethod
    async def collect_news(self) -> List[NewsItem]:
        """Collect news from the source"""
        pass
    
    def calculate_relevance_score(self, title: str, content: str) -> float:
        """Calculate relevance score based on F1 keywords"""
        text = f"{title} {content}".lower()
        
        # Count keyword matches
        keyword_matches = sum(1 for keyword in F1_KEYWORDS if keyword.lower() in text)
        
        # Calculate score (0.0 to 1.0)
        max_keywords = len(F1_KEYWORDS)
        base_score = min(keyword_matches / 10, 1.0)  # Normalize to 0-1
        
        # Boost score for important keywords
        important_keywords = ["formula 1", "f1", "grand prix", "racing", "championship"]
        important_matches = sum(1 for keyword in important_keywords if keyword in text)
        boost = min(important_matches * 0.2, 0.5)
        
        return min(base_score + boost, 1.0)
    
    def extract_keywords(self, title: str, content: str) -> List[str]:
        """Extract relevant keywords from title and content"""
        text = f"{title} {content}".lower()
        found_keywords = [keyword for keyword in F1_KEYWORDS if keyword.lower() in text]
        return list(set(found_keywords))
    
    def clean_content(self, content: str) -> str:
        """Clean and normalize content"""
        # Remove HTML tags
        content = re.sub(r'<[^>]+>', '', content)
        # Remove extra whitespace
        content = re.sub(r'\s+', ' ', content)
        # Remove special characters but keep basic punctuation
        content = re.sub(r'[^\w\s.,!?;:-]', '', content)
        return content.strip()
    
    def is_duplicate(self, title: str, content: str, existing_items: List[NewsItem]) -> bool:
        """Check if news item is duplicate"""
        title_lower = title.lower()
        content_lower = content.lower()
        
        for item in existing_items:
            # Check title similarity
            if self._calculate_similarity(title_lower, item.title.lower()) > 0.8:
                return True
            # Check content similarity for first 200 characters
            if self._calculate_similarity(
                content_lower[:200], 
                item.content.lower()[:200]
            ) > 0.7:
                return True
        
        return False
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity using simple word overlap"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
