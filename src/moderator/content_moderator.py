"""
Content moderator for filtering and quality control
"""
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from ..models import ProcessedNewsItem, NewsItem
from ..config import settings, F1_KEYWORDS

logger = logging.getLogger(__name__)

class ContentModerator:
    """Content moderator for quality control and filtering"""
    
    def __init__(self):
        self.spam_keywords = [
            'spam', 'scam', 'fake', 'clickbait', 'advertisement', 'promo',
            'buy now', 'discount', 'sale', 'free money', 'win big'
        ]
        
        self.quality_keywords = [
            'breaking', 'exclusive', 'official', 'confirmed', 'report',
            'analysis', 'insight', 'update', 'news', 'announcement'
        ]
        
        self.importance_boosters = [
            'championship', 'title', 'pole position', 'victory', 'crash',
            'injury', 'contract', 'transfer', 'retirement', 'comeback'
        ]
    
    def moderate_news_item(self, news_item: ProcessedNewsItem) -> Dict[str, Any]:
        """Moderate a news item and return moderation result"""
        moderation_result = {
            'approved': True,
            'quality_score': 0.0,
            'reasons': [],
            'suggestions': []
        }
        
        try:
            # Check for spam
            if self._is_spam(news_item):
                moderation_result['approved'] = False
                moderation_result['reasons'].append('Spam content detected')
                return moderation_result
            
            # Calculate quality score
            quality_score = self._calculate_quality_score(news_item)
            moderation_result['quality_score'] = quality_score
            
            # Check minimum quality threshold
            if quality_score < 0.3:
                moderation_result['approved'] = False
                moderation_result['reasons'].append('Low quality content')
            
            # Check relevance
            if not self._is_relevant(news_item):
                moderation_result['approved'] = False
                moderation_result['reasons'].append('Not relevant to F1')
            
            # Check for duplicates
            if self._is_duplicate(news_item):
                moderation_result['approved'] = False
                moderation_result['reasons'].append('Duplicate content')
            
            # Check content length
            if len(news_item.content) < 50:
                moderation_result['approved'] = False
                moderation_result['reasons'].append('Content too short')
            
            # Check for proper formatting
            if not self._is_properly_formatted(news_item):
                moderation_result['suggestions'].append('Improve formatting')
            
            # Check for important keywords
            if self._has_important_keywords(news_item):
                moderation_result['suggestions'].append('High importance content - prioritize')
            
            return moderation_result
            
        except Exception as e:
            logger.error(f"Error moderating news item: {e}")
            moderation_result['approved'] = False
            moderation_result['reasons'].append('Moderation error')
            return moderation_result
    
    def _is_spam(self, news_item: ProcessedNewsItem) -> bool:
        """Check if content is spam"""
        text = f"{news_item.title} {news_item.content}".lower()
        
        # Check for spam keywords
        for keyword in self.spam_keywords:
            if keyword in text:
                return True
        
        # Check for excessive promotional language
        promotional_patterns = [
            r'click here', r'buy now', r'limited time', r'act now',
            r'guaranteed', r'100%', r'free', r'discount'
        ]
        
        for pattern in promotional_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    def _calculate_quality_score(self, news_item: ProcessedNewsItem) -> float:
        """Calculate quality score for news item"""
        score = 0.0
        
        # Base score from relevance
        score += news_item.relevance_score * 0.3
        
        # Content length score
        content_length = len(news_item.content)
        if content_length > 200:
            score += 0.2
        elif content_length > 100:
            score += 0.1
        
        # Quality keywords boost
        text = f"{news_item.title} {news_item.content}".lower()
        quality_matches = sum(1 for keyword in self.quality_keywords if keyword in text)
        score += min(quality_matches * 0.1, 0.3)
        
        # Importance level boost
        score += news_item.importance_level * 0.1
        
        # Sentiment analysis
        if news_item.sentiment == 'positive':
            score += 0.1
        elif news_item.sentiment == 'negative':
            score += 0.05  # Negative news can be important
        
        # Source reliability
        if 'official' in news_item.source.lower():
            score += 0.2
        elif 'formula1.com' in news_item.source.lower():
            score += 0.15
        elif 'motorsport.com' in news_item.source.lower():
            score += 0.1
        
        return min(score, 1.0)
    
    def _is_relevant(self, news_item: ProcessedNewsItem) -> bool:
        """Check if content is relevant to F1"""
        text = f"{news_item.title} {news_item.content}".lower()
        
        # Check for F1 keywords
        f1_matches = sum(1 for keyword in F1_KEYWORDS if keyword.lower() in text)
        
        # Must have at least 2 F1-related keywords
        return f1_matches >= 2
    
    def _is_duplicate(self, news_item: ProcessedNewsItem) -> bool:
        """Check if content is duplicate (simplified check)"""
        # This would typically check against database
        # For now, just check for very similar titles
        title_words = set(news_item.title.lower().split())
        
        # If title is too short, it might be duplicate
        if len(title_words) < 3:
            return True
        
        return False
    
    def _is_properly_formatted(self, news_item: ProcessedNewsItem) -> bool:
        """Check if content is properly formatted"""
        # Check if title is not all caps
        if news_item.title.isupper():
            return False
        
        # Check if content has proper punctuation
        if not re.search(r'[.!?]', news_item.content):
            return False
        
        # Check if content is not just a URL
        if news_item.content.strip().startswith('http'):
            return False
        
        return True
    
    def _has_important_keywords(self, news_item: ProcessedNewsItem) -> bool:
        """Check if content has important keywords"""
        text = f"{news_item.title} {news_item.content}".lower()
        
        important_matches = sum(1 for keyword in self.importance_boosters if keyword in text)
        return important_matches > 0
    
    def get_moderation_stats(self) -> Dict[str, Any]:
        """Get moderation statistics"""
        return {
            'spam_keywords_count': len(self.spam_keywords),
            'quality_keywords_count': len(self.quality_keywords),
            'importance_boosters_count': len(self.importance_boosters),
            'f1_keywords_count': len(F1_KEYWORDS)
        }
    
    def update_moderation_rules(self, rules: Dict[str, Any]):
        """Update moderation rules"""
        if 'spam_keywords' in rules:
            self.spam_keywords.extend(rules['spam_keywords'])
        
        if 'quality_keywords' in rules:
            self.quality_keywords.extend(rules['quality_keywords'])
        
        if 'importance_boosters' in rules:
            self.importance_boosters.extend(rules['importance_boosters'])
        
        logger.info("Moderation rules updated")
