"""Unit tests for simulation engine."""

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
