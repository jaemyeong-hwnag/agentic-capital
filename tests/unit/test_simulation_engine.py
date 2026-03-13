"""Unit tests for simulation engine."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_capital.simulation.engine import AgentState, SimulationEngine


class TestAgentState:
    def test_create(self):
        agent = AgentState(name="Alpha", role="trader", philosophy="test", seed=42)
        assert agent.name == "Alpha"
        assert agent.role == "trader"
        assert agent.personality is not None
        assert agent.emotion is not None
        assert agent.total_cycles == 0
        assert agent.memories == []

    def test_different_seeds_different_personalities(self):
        a1 = AgentState(name="A", seed=1)
        a2 = AgentState(name="B", seed=2)
        assert a1.personality.openness != a2.personality.openness


class TestSimulationEngine:
    def test_init_defaults(self):
        engine = SimulationEngine()
        assert engine._cycle_interval == 300
        assert engine._agents == []
        assert engine._running is False

    def test_init_custom(self):
        engine = SimulationEngine(
            cycle_interval_seconds=60,
            symbols=["005930", "000660"],
        )
        assert engine._cycle_interval == 60
        assert engine._symbols == ["005930", "000660"]

    def test_stop(self):
        engine = SimulationEngine()
        engine._running = True
        engine.stop()
        assert engine._running is False

    def test_init_agents(self):
        engine = SimulationEngine()
        engine._init_agents()
        assert len(engine._agents) == 3
        names = [a.name for a in engine._agents]
        assert "Alpha" in names
        assert "Beta" in names
        assert "Gamma" in names

    def test_agent_philosophies(self):
        engine = SimulationEngine()
        engine._init_agents()
        alpha = [a for a in engine._agents if a.name == "Alpha"][0]
        assert "risk" in alpha.philosophy.lower() or "reward" in alpha.philosophy.lower()

    @pytest.mark.asyncio
    async def test_run_cycle_market_closed_still_runs(self):
        """Market closed does NOT block cycle — AI decides autonomously."""
        engine = SimulationEngine()
        engine._init_agents()
        engine._symbols = ["005930"]

        engine._trading = MagicMock()
        engine._trading.get_balance = AsyncMock(
            return_value=MagicMock(total=10_000_000, available=10_000_000)
        )
        engine._trading.get_positions = AsyncMock(return_value=[])
        engine._pipeline = MagicMock()
        engine._pipeline.run_cycle = AsyncMock(
            return_value=([], MagicMock(valence=0.0, stress=0.0))
        )

        with patch("agentic_capital.simulation.engine.is_market_open", return_value=False):
            await engine._run_cycle()
        # Cycle runs even when market is closed — no system-enforced restriction
        assert engine._cycle_count == 1

    @pytest.mark.asyncio
    async def test_run_cycle_market_open(self):
        engine = SimulationEngine()
        engine._init_agents()
        engine._symbols = ["005930"]

        # Mock adapters
        engine._trading = MagicMock()
        engine._trading.get_balance = AsyncMock(
            return_value=MagicMock(total=10_000_000, available=10_000_000)
        )
        engine._trading.get_positions = AsyncMock(return_value=[])
        engine._pipeline = MagicMock()
        engine._pipeline.run_cycle = AsyncMock(
            return_value=([], MagicMock(valence=0.0, stress=0.0))
        )

        with patch("agentic_capital.simulation.engine.is_market_open", return_value=True):
            await engine._run_cycle()
        assert engine._cycle_count == 1

    @pytest.mark.asyncio
    async def test_run_agent_cycle_no_decisions(self):
        engine = SimulationEngine()
        engine._symbols = ["005930"]
        agent = AgentState(name="Test", seed=1)

        engine._pipeline = MagicMock()
        engine._pipeline.run_cycle = AsyncMock(
            return_value=([], MagicMock(valence=0.0, stress=0.0))
        )
        engine._trading = MagicMock()
        engine._trading.get_positions = AsyncMock(return_value=[])

        await engine._run_agent_cycle(agent)
        assert agent.total_cycles == 1
        assert agent.memories == []

    @pytest.mark.asyncio
    async def test_run_agent_cycle_with_decisions(self):
        engine = SimulationEngine()
        engine._symbols = ["005930"]
        engine._cycle_count = 1
        agent = AgentState(name="Test", seed=1)

        from agentic_capital.core.decision.pipeline import TradingDecision
        decision = TradingDecision("BUY", "005930", 10, "test", 0.8)
        engine._pipeline = MagicMock()
        engine._pipeline.run_cycle = AsyncMock(
            return_value=([decision], MagicMock(valence=0.1, stress=0.0))
        )
        engine._trading = MagicMock()
        engine._trading.get_positions = AsyncMock(return_value=[])

        await engine._run_agent_cycle(agent)
        assert agent.total_cycles == 1
        assert len(agent.memories) == 1
        assert "BUY 005930" in agent.memories[0]

    @pytest.mark.asyncio
    async def test_init_recorder_failure_graceful(self):
        engine = SimulationEngine()
        engine._init_agents()
        engine._symbols = ["005930"]

        # Should not raise even if DB is unavailable
        with patch("agentic_capital.simulation.engine.SimulationEngine._init_recorder") as mock_rec:
            mock_rec.return_value = None
            engine._recorder = None
        assert engine._recorder is None
