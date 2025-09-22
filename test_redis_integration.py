#!/usr/bin/env python3
"""
Test script for Redis integration
"""
import asyncio
import sys
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.services.redis_service import redis_service
from src.database import db_manager
from src.models import ProcessedNewsItem, SourceType
from datetime import datetime

async def test_redis_integration():
    """Test Redis integration"""
    print("🧪 Testing Redis integration...")
    
    # Test 1: Check Redis connection
    print("\n1. Testing Redis connection...")
    health = await redis_service.health_check()
    print(f"   Redis health: {'✅ OK' if health else '❌ FAILED'}")
    
    # Test 2: Get processed news from database
    print("\n2. Getting processed news from database...")
    processed_news = await db_manager.get_news_for_publication(limit=3)
    print(f"   Found {len(processed_news)} processed news items")
    
    if processed_news:
        # Test 3: Add news to Redis queue
        print("\n3. Adding news to Redis queue...")
        for news_item in processed_news:
            success = await redis_service.add_news_to_moderation_queue(news_item)
            print(f"   Added '{news_item.title[:50]}...': {'✅ OK' if success else '❌ FAILED'}")
        
        # Test 4: Check Redis queue length
        print("\n4. Checking Redis queue length...")
        queue_length = await redis_service.get_moderation_queue_length()
        print(f"   Queue length: {queue_length}")
        
        # Test 5: Get news from Redis queue
        print("\n5. Getting news from Redis queue...")
        redis_news = await redis_service.get_news_from_moderation_queue(limit=5)
        print(f"   Retrieved {len(redis_news)} news items from Redis")
        
        for news_item in redis_news:
            print(f"   - {news_item.title[:50]}...")
    
    # Test 6: Check queue status
    print("\n6. Checking queue status...")
    status = await redis_service.get_queue_status()
    print(f"   Status: {status}")
    
    print("\n✅ Redis integration test completed!")

if __name__ == "__main__":
    asyncio.run(test_redis_integration())
