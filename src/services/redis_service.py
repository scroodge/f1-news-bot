"""
Redis service — wake-up signals only.

PostgreSQL is the single source of truth for queue state; Redis just lets one
process nudge another ("new items are waiting") without polling the DB hard.
Consumers may also simply poll the DB — the signal is an optimization, not a
required part of the pipeline.
"""

import logging

import redis.asyncio as redis

from ..config import settings

logger = logging.getLogger(__name__)

PENDING_SIGNAL_KEY = "f1_news:pending_signal"


class RedisService:
    """Thin wake-up-signal layer between the main app and the bot"""

    def __init__(self):
        self.client = redis.from_url(settings.redis_url)

    async def ping(self) -> bool:
        try:
            return await self.client.ping()
        except Exception as e:
            logger.error(f"Redis ping failed: {e}")
            return False

    async def signal_new_pending(self, count: int = 1) -> None:
        """Called by the processor when items land in the moderation queue"""
        try:
            await self.client.incrby(PENDING_SIGNAL_KEY, count)
        except Exception as e:
            logger.warning(f"Redis signal failed (non-fatal): {e}")

    async def consume_pending_signal(self) -> int:
        """Called by the bot: returns and resets the new-items counter"""
        try:
            value = await self.client.getdel(PENDING_SIGNAL_KEY)
            return int(value) if value else 0
        except Exception as e:
            logger.warning(f"Redis signal read failed (non-fatal): {e}")
            return 0

    async def close(self):
        await self.client.aclose()


# Global instance
redis_service = RedisService()
