"""Integration tests — real Redis for Working Memory."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from agentic_capital.core.memory.working import WorkingMemory


@pytest.mark.integration
class TestWorkingMemoryRedis:
    @pytest.mark.asyncio
    async def test_add_and_get_observations(self, redis_client, agent_id: uuid.UUID) -> None:
        wm = WorkingMemory(redis_client)

        await wm.add_observation(agent_id, {"symbol": "AAPL", "close": 150.0})
        await wm.add_observation(agent_id, {"symbol": "MSFT", "close": 300.0})

        obs = await wm.get_observations(agent_id)
        assert len(obs) == 2
        assert obs[0]["symbol"] == "MSFT"  # newest first
        assert obs[1]["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_max_observations_trim(self, redis_client, agent_id: uuid.UUID) -> None:
        wm = WorkingMemory(redis_client)
        wm.MAX_OBSERVATIONS = 3

        for i in range(5):
            await wm.add_observation(agent_id, {"idx": i})

        obs = await wm.get_observations(agent_id)
        assert len(obs) == 3
        assert obs[0]["idx"] == 4  # newest

    @pytest.mark.asyncio
    async def test_task_crud(self, redis_client, agent_id: uuid.UUID) -> None:
        wm = WorkingMemory(redis_client)

        assert await wm.get_current_task(agent_id) is None

        await wm.set_current_task(agent_id, {"action": "analyze", "target": "TSLA"})
        task = await wm.get_current_task(agent_id)
        assert task is not None
        assert task["target"] == "TSLA"

    @pytest.mark.asyncio
    async def test_context_crud(self, redis_client, agent_id: uuid.UUID) -> None:
        wm = WorkingMemory(redis_client)

        await wm.set_context(agent_id, {"valence": 0.7, "market": "bullish"})
        ctx = await wm.get_context(agent_id)
        assert ctx is not None
        assert ctx["valence"] == 0.7

    @pytest.mark.asyncio
    async def test_snapshot(self, redis_client, agent_id: uuid.UUID) -> None:
        wm = WorkingMemory(redis_client)

        await wm.add_observation(agent_id, {"price": 100})
        await wm.set_current_task(agent_id, {"action": "buy"})
        await wm.set_context(agent_id, {"mood": "positive"})

        snap = await wm.snapshot(agent_id)
        assert len(snap["observations"]) == 1
        assert snap["current_task"]["action"] == "buy"
        assert snap["context"]["mood"] == "positive"

    @pytest.mark.asyncio
    async def test_clear(self, redis_client, agent_id: uuid.UUID) -> None:
        wm = WorkingMemory(redis_client)

        await wm.add_observation(agent_id, {"test": True})
        await wm.set_current_task(agent_id, {"action": "test"})
        await wm.set_context(agent_id, {"ctx": True})

        await wm.clear(agent_id)

        assert await wm.get_observations(agent_id) == []
        assert await wm.get_current_task(agent_id) is None
        assert await wm.get_context(agent_id) is None
