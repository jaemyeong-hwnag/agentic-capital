"""Redis async client for working memory and event streams."""

import structlog
import redis.asyncio as aioredis

from agentic_capital.config import settings

logger = structlog.get_logger()

redis_client = aioredis.from_url(
    settings.redis_url,
    decode_responses=True,
)

logger.info("redis_client_created", url=settings.redis_url)


async def get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    """Get the Redis async client."""
    return redis_client
