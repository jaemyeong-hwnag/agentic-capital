"""Working memory — short-term context stored in Redis.

Stores the latest observations and current task context per agent.
TTL-based expiration ensures automatic cleanup.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import orjson
import redis.asyncio as aioredis


class WorkingMemory:
    """Redis-backed short-term memory for agent context."""

    KEY_PREFIX = "wm"
    DEFAULT_TTL = timedelta(hours=1)
    MAX_OBSERVATIONS = 10

    def __init__(self, redis: aioredis.Redis) -> None:  # type: ignore[type-arg]
        self._redis = redis

    def _obs_key(self, agent_id: uuid.UUID) -> str:
        return f"{self.KEY_PREFIX}:{agent_id}:observations"

    def _task_key(self, agent_id: uuid.UUID) -> str:
        return f"{self.KEY_PREFIX}:{agent_id}:task"

    def _ctx_key(self, agent_id: uuid.UUID) -> str:
        return f"{self.KEY_PREFIX}:{agent_id}:context"

    async def add_observation(
        self,
        agent_id: uuid.UUID,
        observation: dict,
        *,
        ttl: timedelta | None = None,
    ) -> None:
        """Push an observation and trim to MAX_OBSERVATIONS."""
        key = self._obs_key(agent_id)
        data = orjson.dumps(observation).decode()
        ttl_seconds = int((ttl or self.DEFAULT_TTL).total_seconds())
        await self._redis.lpush(key, data)
        await self._redis.ltrim(key, 0, self.MAX_OBSERVATIONS - 1)
        await self._redis.expire(key, ttl_seconds)

    async def get_observations(self, agent_id: uuid.UUID, limit: int = 10) -> list[dict]:
        """Get recent observations (newest first)."""
        key = self._obs_key(agent_id)
        items = await self._redis.lrange(key, 0, limit - 1)
        return [orjson.loads(item) for item in items]

    async def set_current_task(
        self,
        agent_id: uuid.UUID,
        task: dict,
        *,
        ttl: timedelta | None = None,
    ) -> None:
        """Set the agent's current task."""
        key = self._task_key(agent_id)
        data = orjson.dumps(task).decode()
        await self._redis.set(key, data, ex=int((ttl or self.DEFAULT_TTL).total_seconds()))

    async def get_current_task(self, agent_id: uuid.UUID) -> dict | None:
        """Get the agent's current task."""
        key = self._task_key(agent_id)
        data = await self._redis.get(key)
        if data is None:
            return None
        return orjson.loads(data)

    async def set_context(
        self,
        agent_id: uuid.UUID,
        context: dict,
        *,
        ttl: timedelta | None = None,
    ) -> None:
        """Set arbitrary context data (emotion state, market snapshot, etc.)."""
        key = self._ctx_key(agent_id)
        data = orjson.dumps(context).decode()
        await self._redis.set(key, data, ex=int((ttl or self.DEFAULT_TTL).total_seconds()))

    async def get_context(self, agent_id: uuid.UUID) -> dict | None:
        """Get the agent's context data."""
        key = self._ctx_key(agent_id)
        data = await self._redis.get(key)
        if data is None:
            return None
        return orjson.loads(data)

    async def clear(self, agent_id: uuid.UUID) -> None:
        """Clear all working memory for an agent."""
        keys = [
            self._obs_key(agent_id),
            self._task_key(agent_id),
            self._ctx_key(agent_id),
        ]
        await self._redis.delete(*keys)

    async def snapshot(self, agent_id: uuid.UUID) -> dict:
        """Get full working memory snapshot for prompt construction."""
        observations = await self.get_observations(agent_id)
        task = await self.get_current_task(agent_id)
        context = await self.get_context(agent_id)
        return {
            "observations": observations,
            "current_task": task,
            "context": context,
        }
