"""
Base collector class for all data sources
"""
import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
import re

from ..models import NewsItem, SourceType
from ..config import F1_KEYWORDS, HIGH_PRIORITY_KEYWORDS, TEAM_NAMES, DRIVER_NAMES

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
        """Calculate professional relevance score based on F1 keywords"""
        text = f"{title} {content}".lower()
        
        # Initialize score components
        base_score = 0.0
        title_boost = 0.0
        priority_boost = 0.0
        team_driver_boost = 0.0
        
        # 1. Count general F1 keyword matches
        keyword_matches = sum(1 for keyword in F1_KEYWORDS if keyword.lower() in text)
        if keyword_matches > 0:
            base_score = min(keyword_matches * 0.1, 0.6)  # Max 0.6 for general keywords
        
        # 2. High-priority keyword boost (strong F1 indicators)
        priority_matches = sum(1 for keyword in HIGH_PRIORITY_KEYWORDS if keyword in text)
        if priority_matches > 0:
            priority_boost = min(priority_matches * 0.3, 0.8)  # Max 0.8 for priority keywords
        
        # 3. Team and driver name boost
        team_matches = sum(1 for team in TEAM_NAMES if team in text)
        driver_matches = sum(1 for driver in DRIVER_NAMES if driver in text)
        if team_matches > 0 or driver_matches > 0:
            team_driver_boost = min((team_matches + driver_matches) * 0.2, 0.6)
        
        # 4. Title boost (titles are more important than content)
        title_text = title.lower()
        title_keyword_matches = sum(1 for keyword in F1_KEYWORDS if keyword.lower() in title_text)
        title_priority_matches = sum(1 for keyword in HIGH_PRIORITY_KEYWORDS if keyword in title_text)
        
        if title_keyword_matches > 0:
            title_boost = min(title_keyword_matches * 0.15, 0.4)
        if title_priority_matches > 0:
            title_boost += min(title_priority_matches * 0.25, 0.5)
        
        # 5. Special F1 terms boost
        special_terms = ["grand prix", "гран при", "qualifying", "квалификация", 
                        "pole position", "поул позиция", "podium", "подиум",
                        "championship", "чемпионат", "race", "гонка"]
        special_matches = sum(1 for term in special_terms if term in text)
        special_boost = min(special_matches * 0.1, 0.3)
        
        # Calculate final score
        final_score = base_score + priority_boost + team_driver_boost + title_boost + special_boost
        
        # Ensure score is between 0.0 and 1.0
        final_score = max(0.0, min(final_score, 1.0))
        
        # Minimum threshold: if any F1 keyword is found, give at least 0.1
        if keyword_matches > 0 and final_score < 0.1:
            final_score = 0.1
        
        return final_score
    
    def extract_keywords(self, title: str, content: str) -> List[str]:
        """Extract relevant keywords from title and content"""
        text = f"{title} {content}".lower()
        found_keywords = []
        
        # Extract general F1 keywords
        found_keywords.extend([keyword for keyword in F1_KEYWORDS if keyword.lower() in text])
        
        # Extract high-priority keywords
        found_keywords.extend([keyword for keyword in HIGH_PRIORITY_KEYWORDS if keyword in text])
        
        # Extract team names
        found_keywords.extend([team for team in TEAM_NAMES if team in text])
        
        # Extract driver names
        found_keywords.extend([driver for driver in DRIVER_NAMES if driver in text])
        
        # Remove duplicates and return
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
