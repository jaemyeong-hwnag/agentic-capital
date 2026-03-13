"""Tests for Redis Working Memory."""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from agentic_capital.core.memory.working import WorkingMemory


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Create a mock Redis client."""
    redis = AsyncMock()
    return redis


@pytest.fixture
def wm(mock_redis: AsyncMock) -> WorkingMemory:
    return WorkingMemory(mock_redis)


@pytest.fixture
def agent_id() -> uuid.UUID:
    return uuid.uuid4()


class TestWorkingMemory:
    @pytest.mark.asyncio
    async def test_add_observation(self, wm: WorkingMemory, mock_redis: AsyncMock, agent_id: uuid.UUID) -> None:
        await wm.add_observation(agent_id, {"type": "price", "symbol": "AAPL", "close": 150.0})
        mock_redis.lpush.assert_awaited_once()
        mock_redis.ltrim.assert_awaited_once()
        mock_redis.expire.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_observations(self, wm: WorkingMemory, mock_redis: AsyncMock, agent_id: uuid.UUID) -> None:
        import orjson
        items = [
            orjson.dumps({"symbol": "AAPL", "close": 150.0}).decode(),
            orjson.dumps({"symbol": "MSFT", "close": 300.0}).decode(),
        ]
        mock_redis.lrange.return_value = items
        result = await wm.get_observations(agent_id, limit=5)
        assert len(result) == 2
        assert result[0]["symbol"] == "AAPL"
        assert result[1]["symbol"] == "MSFT"

    @pytest.mark.asyncio
    async def test_set_and_get_task(self, wm: WorkingMemory, mock_redis: AsyncMock, agent_id: uuid.UUID) -> None:
        import orjson
        task = {"action": "analyze", "target": "TSLA"}
        await wm.set_current_task(agent_id, task)
        mock_redis.set.assert_awaited_once()

        mock_redis.get.return_value = orjson.dumps(task).decode()
        result = await wm.get_current_task(agent_id)
        assert result == task

    @pytest.mark.asyncio
    async def test_get_task_none(self, wm: WorkingMemory, mock_redis: AsyncMock, agent_id: uuid.UUID) -> None:
        mock_redis.get.return_value = None
        result = await wm.get_current_task(agent_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get_context(self, wm: WorkingMemory, mock_redis: AsyncMock, agent_id: uuid.UUID) -> None:
        import orjson
        ctx = {"valence": 0.6, "arousal": 0.4, "market": "bullish"}
        await wm.set_context(agent_id, ctx)
        mock_redis.set.assert_awaited()

        mock_redis.get.return_value = orjson.dumps(ctx).decode()
        result = await wm.get_context(agent_id)
        assert result == ctx

    @pytest.mark.asyncio
    async def test_clear(self, wm: WorkingMemory, mock_redis: AsyncMock, agent_id: uuid.UUID) -> None:
        await wm.clear(agent_id)
        mock_redis.delete.assert_awaited_once()
        args = mock_redis.delete.call_args[0]
        assert len(args) == 3  # observations, task, context keys

    @pytest.mark.asyncio
    async def test_snapshot(self, wm: WorkingMemory, mock_redis: AsyncMock, agent_id: uuid.UUID) -> None:
        import orjson
        mock_redis.lrange.return_value = [orjson.dumps({"price": 100}).decode()]
        mock_redis.get.side_effect = [
            orjson.dumps({"action": "buy"}).decode(),
            orjson.dumps({"mood": "positive"}).decode(),
        ]
        snap = await wm.snapshot(agent_id)
        assert "observations" in snap
        assert "current_task" in snap
        assert "context" in snap
        assert len(snap["observations"]) == 1

    @pytest.mark.asyncio
    async def test_custom_ttl(self, wm: WorkingMemory, mock_redis: AsyncMock, agent_id: uuid.UUID) -> None:
        await wm.add_observation(agent_id, {"test": True}, ttl=timedelta(minutes=30))
        expire_args = mock_redis.expire.call_args[0]
        assert expire_args[1] == 1800  # 30 minutes in seconds

    def test_key_prefixes(self, wm: WorkingMemory, agent_id: uuid.UUID) -> None:
        assert wm._obs_key(agent_id).startswith("wm:")
        assert wm._task_key(agent_id).endswith(":task")
        assert wm._ctx_key(agent_id).endswith(":context")
