"""Unit tests for simulation engine."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agentic_capital.core.agents.base import AgentProfile
from agentic_capital.core.agents.ceo import CEOAgent
from agentic_capital.core.agents.analyst import AnalystAgent
from agentic_capital.core.agents.factory import create_random_personality
from agentic_capital.core.personality.models import PersonalityVector
from agentic_capital.ports.llm import LLMPort
from agentic_capital.simulation.engine import SimulationEngine


def _make_llm(response='{"actions": [], "confidence": 0.5}'):
    llm = MagicMock(spec=LLMPort)
    llm.generate = AsyncMock(return_value=response)
    llm.embed = AsyncMock(return_value=[0.0] * 1024)
    return llm


def _make_profile(name="Test"):
    return AgentProfile(id=uuid4(), name=name, philosophy="test")


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
        llm = _make_llm()
        engine._llm = llm
        trading = MagicMock()
        market_data = MagicMock()
        engine._trading = trading
        engine._market_data = market_data

        # Patch create_agent to avoid type checks on mock
        with patch("agentic_capital.simulation.engine.create_agent") as mock_create:
            agents = [
                CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm),
                AnalystAgent(profile=_make_profile("Analyst"), personality=create_random_personality(43), llm=llm),
                MagicMock(name="Trader", agent_id=uuid4(), personality=create_random_personality(44)),
            ]
            agents[2].name = "Trader"
            agents[2].profile = _make_profile("Trader")
            mock_create.side_effect = agents
            engine._init_agents()

        assert len(engine._agents) == 3

    @pytest.mark.asyncio
    async def test_run_cycle(self):
        engine = SimulationEngine()
        engine._symbols = ["005930"]

        # Create mock agents
        llm = _make_llm()
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        analyst = AnalystAgent(profile=_make_profile("Analyst"), personality=create_random_personality(43), llm=llm)
        engine._agents = [ceo, analyst]

        engine._trading = MagicMock()
        engine._trading.get_balance = AsyncMock(
            return_value=MagicMock(total=10_000_000, available=10_000_000)
        )

        with patch("agentic_capital.simulation.engine.run_agent_cycle", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {"decisions": [], "emotion": {}}
            await engine._run_cycle()

        assert engine._cycle_count == 1
        assert mock_run.call_count == 2  # CEO + Analyst

    @pytest.mark.asyncio
    async def test_run_cycle_market_closed_still_runs(self):
        """Market closed does NOT block cycle — AI decides autonomously."""
        engine = SimulationEngine()
        engine._symbols = ["005930"]
        llm = _make_llm()
        engine._agents = [
            CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm),
        ]
        engine._trading = MagicMock()
        engine._trading.get_balance = AsyncMock(
            return_value=MagicMock(total=10_000_000, available=10_000_000)
        )

        with patch("agentic_capital.simulation.engine.run_agent_cycle", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {"decisions": [], "emotion": {}}
            with patch("agentic_capital.simulation.engine.is_market_open", return_value=False):
                await engine._run_cycle()

        assert engine._cycle_count == 1

    @pytest.mark.asyncio
    async def test_process_org_actions_hire(self):
        engine = SimulationEngine()
        llm = _make_llm()
        engine._llm = llm
        engine._trading = MagicMock()
        engine._market_data = MagicMock()

        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        engine._agents = [ceo]

        result = {
            "decisions": [{"type": "hire", "target": "NewTrader", "detail": "analyst", "reason": "need analysis"}],
        }

        with patch("agentic_capital.simulation.engine.create_agent") as mock_create:
            new_agent = AnalystAgent(profile=_make_profile("NewTrader"), personality=create_random_personality(99), llm=llm)
            mock_create.return_value = new_agent
            await engine._process_org_actions(ceo, result)

        assert len(engine._agents) == 2
        assert engine._agents[1].name == "NewTrader"

    @pytest.mark.asyncio
    async def test_process_org_actions_fire(self):
        engine = SimulationEngine()
        llm = _make_llm()

        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        target = AnalystAgent(profile=_make_profile("BadAgent"), personality=create_random_personality(99), llm=llm)
        engine._agents = [ceo, target]

        result = {
            "decisions": [{"type": "fire", "target": "BadAgent", "reason": "poor performance"}],
        }

        await engine._process_org_actions(ceo, result)
        assert len(engine._agents) == 1
        assert engine._agents[0].name == "CEO"

    @pytest.mark.asyncio
    async def test_process_org_actions_fire_self_prevented(self):
        """CEO cannot fire itself."""
        engine = SimulationEngine()
        llm = _make_llm()

        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        engine._agents = [ceo]

        result = {"decisions": [{"type": "fire", "target": "CEO"}]}
        await engine._process_org_actions(ceo, result)
        assert len(engine._agents) == 1  # CEO still there

    @pytest.mark.asyncio
    async def test_process_org_actions_non_ceo_ignored(self):
        """Non-CEO agents' org actions are not processed."""
        engine = SimulationEngine()
        llm = _make_llm()

        analyst = AnalystAgent(profile=_make_profile("Analyst"), personality=create_random_personality(42), llm=llm)
        engine._agents = [analyst]

        result = {"decisions": [{"type": "fire", "target": "someone"}]}
        await engine._process_org_actions(analyst, result)
        assert len(engine._agents) == 1

    @pytest.mark.asyncio
    async def test_process_org_actions_create_role(self):
        engine = SimulationEngine()
        llm = _make_llm()

        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        engine._agents = [ceo]
        engine._recorder = MagicMock()
        engine._recorder.record_role = AsyncMock(return_value=uuid4())

        result = {"decisions": [{"type": "create_role", "detail": "risk_manager"}]}
        await engine._process_org_actions(ceo, result)
        engine._recorder.record_role.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_cycle_with_recorder(self):
        engine = SimulationEngine()
        engine._symbols = ["005930"]
        llm = _make_llm()
        engine._agents = [
            CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm),
        ]

        engine._trading = MagicMock()
        engine._trading.get_balance = AsyncMock(
            return_value=MagicMock(total=10_000_000, available=10_000_000)
        )

        engine._recorder = MagicMock()
        engine._recorder.record_company_snapshot = AsyncMock()
        engine._recorder.commit = AsyncMock()

        with patch("agentic_capital.simulation.engine.run_agent_cycle", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {"decisions": [], "emotion": {}}
            await engine._run_cycle()

        engine._recorder.record_company_snapshot.assert_called_once()
        engine._recorder.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_fire_with_recorder(self):
        engine = SimulationEngine()
        llm = _make_llm()

        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        target = AnalystAgent(profile=_make_profile("BadAgent"), personality=create_random_personality(99), llm=llm)
        engine._agents = [ceo, target]

        engine._recorder = MagicMock()
        engine._recorder.record_hr_event = AsyncMock()
        engine._recorder.record_agent_status_change = AsyncMock()

        result = {"decisions": [{"type": "fire", "target": "BadAgent", "reason": "underperforming"}]}
        await engine._process_org_actions(ceo, result)

        assert len(engine._agents) == 1
        engine._recorder.record_hr_event.assert_called_once()
        engine._recorder.record_agent_status_change.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_recorder_failure_graceful(self):
        engine = SimulationEngine()
        engine._agents = []
        engine._symbols = ["005930"]

        with patch("agentic_capital.simulation.engine.SimulationEngine._init_recorder") as mock_rec:
            mock_rec.return_value = None
            engine._recorder = None
        assert engine._recorder is None

    @pytest.mark.asyncio
    async def test_process_org_actions_abolish_role(self):
        """CEO can abolish a role."""
        engine = SimulationEngine()
        llm = _make_llm()
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        engine._agents = [ceo]
        engine._recorder = MagicMock()
        engine._recorder.record_role = AsyncMock(return_value=None)

        result = {"decisions": [{"type": "abolish_role", "detail": "risk_manager"}]}
        await engine._process_org_actions(ceo, result)
        engine._recorder.record_role.assert_called_once()

    @pytest.mark.asyncio
    async def test_hire_with_recorder(self):
        """Hire action records agent and HR event when recorder is present."""
        engine = SimulationEngine()
        llm = _make_llm()
        engine._llm = llm
        engine._trading = MagicMock()
        engine._market_data = MagicMock()

        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        engine._agents = [ceo]

        engine._recorder = MagicMock()
        engine._recorder.record_agent = AsyncMock()
        engine._recorder.record_hr_event = AsyncMock()
        engine._recorder.commit = AsyncMock()

        result = {
            "decisions": [{"type": "hire", "target": "NewAnalyst", "detail": "analyst", "reason": "need analysis"}],
        }

        with patch("agentic_capital.simulation.engine.create_agent") as mock_create:
            new_agent = AnalystAgent(profile=_make_profile("NewAnalyst"), personality=create_random_personality(99), llm=llm)
            mock_create.return_value = new_agent
            await engine._process_org_actions(ceo, result)

        assert len(engine._agents) == 2
        engine._recorder.record_agent.assert_called_once()
        engine._recorder.record_hr_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_role_no_detail_skips(self):
        """create_role with empty detail is silently skipped."""
        engine = SimulationEngine()
        llm = _make_llm()
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        engine._agents = [ceo]
        engine._recorder = MagicMock()
        engine._recorder.record_role = AsyncMock()

        result = {"decisions": [{"type": "create_role", "detail": ""}]}
        await engine._process_org_actions(ceo, result)
        engine._recorder.record_role.assert_not_called()

    @pytest.mark.asyncio
    async def test_abolish_role_no_detail_skips(self):
        """abolish_role with empty detail is silently skipped."""
        engine = SimulationEngine()
        llm = _make_llm()
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        engine._agents = [ceo]
        engine._recorder = MagicMock()
        engine._recorder.record_role = AsyncMock()

        result = {"decisions": [{"type": "abolish_role", "detail": ""}]}
        await engine._process_org_actions(ceo, result)
        engine._recorder.record_role.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_cycle_agent_error_continues(self):
        """If one agent's cycle fails, other agents still run."""
        engine = SimulationEngine()
        engine._symbols = ["005930"]
        llm = _make_llm()
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        analyst = AnalystAgent(profile=_make_profile("Analyst"), personality=create_random_personality(43), llm=llm)
        engine._agents = [ceo, analyst]
        engine._trading = MagicMock()
        engine._trading.get_balance = AsyncMock(return_value=MagicMock(total=10_000_000, available=10_000_000))

        call_count = 0

        async def mock_run(agent, cycle_number, **kwargs):
            nonlocal call_count
            call_count += 1
            if agent.name == "CEO":
                raise RuntimeError("CEO cycle failed")
            return {"decisions": [], "emotion": {}}

        with patch("agentic_capital.simulation.engine.run_agent_cycle", side_effect=mock_run):
            await engine._run_cycle()

        assert engine._cycle_count == 1
        assert call_count == 2  # Both agents attempted

    @pytest.mark.asyncio
    async def test_init_recorder_success(self):
        """_init_recorder sets up recorder when DB is available."""
        engine = SimulationEngine()
        llm = _make_llm()
        engine._llm = llm
        engine._agents = [
            CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm),
        ]
        engine._symbols = ["005930"]

        mock_session = MagicMock()
        mock_recorder = MagicMock()
        mock_recorder.start_simulation = AsyncMock(return_value="sim-id-123")
        mock_recorder.record_agent = AsyncMock()
        mock_recorder.commit = AsyncMock()

        with patch("agentic_capital.simulation.recorder.SimulationRecorder", return_value=mock_recorder), \
             patch("agentic_capital.infra.database.async_session", return_value=mock_session):
            await engine._init_recorder()

        assert engine._recorder is mock_recorder
        mock_recorder.start_simulation.assert_called_once()
        mock_recorder.record_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_recorder_db_failure_graceful(self):
        """_init_recorder handles DB errors gracefully, recorder = None."""
        engine = SimulationEngine()
        engine._agents = []
        engine._symbols = []

        with patch("agentic_capital.infra.database.async_session", side_effect=Exception("DB not available")):
            await engine._init_recorder()

        assert engine._recorder is None
