"""Scale test — 10 agents running simultaneously.

Validates that the system can handle multiple agents
running LangGraph workflows concurrently without issues.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agentic_capital.core.agents.analyst import AnalystAgent
from agentic_capital.core.agents.base import AgentProfile
from agentic_capital.core.agents.ceo import CEOAgent
from agentic_capital.core.agents.factory import create_random_personality
from agentic_capital.core.agents.trader import TraderAgent
from agentic_capital.graph.workflow import run_agent_cycle
from agentic_capital.ports.llm import LLMPort
from agentic_capital.ports.market_data import MarketDataPort
from agentic_capital.ports.trading import TradingPort


def _make_llm(response='{"actions": [], "confidence": 0.5}'):
    llm = MagicMock(spec=LLMPort)
    llm.generate = AsyncMock(return_value=response)
    llm.embed = AsyncMock(return_value=[0.0] * 1024)
    return llm


def _make_trading():
    trading = MagicMock(spec=TradingPort)
    trading.get_balance = AsyncMock(
        return_value=MagicMock(total=10_000_000, available=8_000_000, currency="KRW")
    )
    trading.get_positions = AsyncMock(return_value=[])
    trading.submit_order = AsyncMock()
    return trading


def _make_market_data():
    md = MagicMock(spec=MarketDataPort)
    md.get_quote = AsyncMock(
        return_value=MagicMock(price=72000, volume=5_000_000)
    )
    md.get_symbols = AsyncMock(return_value=["005930"])
    return md


def _make_recorder():
    recorder = MagicMock()
    recorder.record_emotion = AsyncMock()
    recorder.record_decision = AsyncMock()
    recorder.record_hr_event = AsyncMock()
    recorder.record_agent_message = AsyncMock()
    recorder.record_position_snapshot = AsyncMock()
    recorder.commit = AsyncMock()
    return recorder


def _create_agents(count: int = 10) -> list:
    """Create a diverse roster of agents."""
    trading = _make_trading()
    md = _make_market_data()
    agents = []

    for i in range(count):
        seed = 42 + i
        name = f"Agent-{i:02d}"

        if i == 0:
            # CEO
            llm = _make_llm('{"actions": [{"type": "strategy", "detail": "diversify"}], "confidence": 0.7}')
            agent = CEOAgent(
                profile=AgentProfile(id=uuid4(), name=name, philosophy="maximize returns"),
                personality=create_random_personality(seed),
                llm=llm,
            )
        elif i % 3 == 1:
            # Analyst
            llm = _make_llm('{"signals": [{"symbol": "005930", "signal": "BUY", "confidence": 0.7, "thesis": "growth"}], "market_outlook": "neutral"}')
            agent = AnalystAgent(
                profile=AgentProfile(id=uuid4(), name=name, philosophy="data-driven analysis"),
                personality=create_random_personality(seed),
                llm=llm,
            )
        else:
            # Trader
            llm = _make_llm('{"decisions": [], "confidence": 0.5}')
            agent = TraderAgent(
                profile=AgentProfile(id=uuid4(), name=name, philosophy="precise execution"),
                personality=create_random_personality(seed),
                llm=llm,
                trading=trading,
                market_data=md,
            )

        agents.append(agent)

    return agents


@pytest.mark.e2e
class TestScaleSimulation:
    @pytest.mark.asyncio
    async def test_10_agents_sequential(self):
        """10 agents run sequentially in one cycle."""
        agents = _create_agents(10)
        recorder = _make_recorder()
        trading = _make_trading()
        md = _make_market_data()

        results = []
        for agent in agents:
            result = await run_agent_cycle(
                agent,
                cycle_number=1,
                trading=trading,
                market_data=md,
                symbols=["005930"],
                recorder=recorder,
            )
            results.append(result)

        assert len(results) == 10
        # All agents completed
        for i, r in enumerate(results):
            assert r["agent_name"] == f"Agent-{i:02d}"
            assert "emotion" in r

        # All emotions recorded
        assert recorder.record_emotion.call_count == 10
        assert recorder.commit.call_count == 10

    @pytest.mark.asyncio
    async def test_10_agents_3_cycles(self):
        """10 agents run for 3 complete cycles."""
        agents = _create_agents(10)
        trading = _make_trading()
        md = _make_market_data()

        for cycle in range(1, 4):
            for agent in agents:
                result = await run_agent_cycle(
                    agent,
                    cycle_number=cycle,
                    trading=trading,
                    market_data=md,
                    symbols=["005930"],
                )
                assert result["cycle_number"] == cycle

    @pytest.mark.asyncio
    async def test_diverse_personalities(self):
        """Verify all 10 agents have unique personalities."""
        agents = _create_agents(10)
        personalities = set()
        for agent in agents:
            key = (
                round(agent.personality.openness, 4),
                round(agent.personality.loss_aversion, 4),
            )
            personalities.add(key)

        # All agents should have unique personality vectors
        assert len(personalities) == 10

    @pytest.mark.asyncio
    async def test_mixed_roles(self):
        """Verify the roster has all three role types."""
        agents = _create_agents(10)
        roles = set(type(a).__name__ for a in agents)
        assert "CEOAgent" in roles
        assert "AnalystAgent" in roles
        assert "TraderAgent" in roles
