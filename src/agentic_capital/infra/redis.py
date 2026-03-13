"""Redis async client for working memory and event streams."""

import redis.asyncio as aioredis

from agentic_capital.config import settings

redis_client = aioredis.from_url(
    settings.redis_url,
    decode_responses=True,
)


async def get_redis() -> aioredis.Redis:  # type: ignore[type-arg]
    """Get the Redis async client."""
    return redis_client
