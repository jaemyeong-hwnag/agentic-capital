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
        assert engine._agents == []
        assert engine._running is False

    def test_init_custom(self):
        engine = SimulationEngine(symbols=["005930", "000660"])
        assert engine._symbols == ["005930", "000660"]

    def test_stop(self):
        engine = SimulationEngine()
        engine._running = True
        engine.stop()
        assert engine._running is False

    def test_startup_gate_validates_local_finance_runtime(self):
        engine = SimulationEngine()
        with patch("agentic_capital.adapters.llm.router.is_local_llm_enabled", return_value=True), \
             patch("agentic_capital.simulation.engine.settings.local_agent_llm_base_url", "http://127.0.0.1:19000/v1"), \
             patch("agentic_capital.adapters.llm.local_finance_runtime.validate_local_finance_runtime") as mock_validate:
            engine._validate_startup_gate()
        mock_validate.assert_called_once()

    def test_startup_gate_rejects_missing_agent_runtime_when_finance_model_is_primary(self):
        engine = SimulationEngine()
        with patch("agentic_capital.adapters.llm.router.is_local_llm_enabled", return_value=True), \
             patch("agentic_capital.simulation.engine.settings.local_llm_model", "finance_decision_model"), \
             patch("agentic_capital.simulation.engine.settings.local_agent_llm_base_url", ""), \
             pytest.raises(RuntimeError, match="LOCAL_AGENT_LLM_BASE_URL"):
            engine._validate_startup_gate()

    def test_startup_gate_validates_finance_pipeline_with_hosted_agent_llm(self):
        engine = SimulationEngine()
        with patch("agentic_capital.adapters.llm.router.is_local_llm_enabled", return_value=False), \
             patch("agentic_capital.simulation.engine.settings.local_finance_pipeline_enabled", True), \
             patch("agentic_capital.adapters.llm.local_finance_runtime.validate_local_finance_runtime") as mock_validate:
            engine._validate_startup_gate()
        mock_validate.assert_called_once()

    def test_cycle_guard_clamps_zero_delay(self):
        engine = SimulationEngine()
        result = engine._apply_cycle_guards(requested_delay=0, total_decisions=1)
        assert result == 60
        assert engine._running is False

    def test_zero_decision_guard_stops_after_threshold(self):
        engine = SimulationEngine()
        engine._running = True
        with patch("agentic_capital.simulation.engine.settings.simulation_zero_decision_max_cycles", 2):
            engine._apply_cycle_guards(requested_delay=60, total_decisions=0)
            engine._apply_cycle_guards(
                requested_delay=60,
                total_decisions=0,
                guard_context={
                    "cause_classification": "finance_sidecar_no_context",
                    "first_failing_stage": "finance_tool_planner_model",
                },
            )
        assert engine._running is False
        assert engine._stop_reason == "zero_decision_guard"
        assert engine._stop_diagnostics["first_failing_stage"] == "finance_tool_planner_model"

    @pytest.mark.asyncio
    async def test_run_cycle_reconciles_broker_positions_after_snapshot(self):
        """Each cycle re-syncs broker positions so paper fills reach the recorder."""
        engine = SimulationEngine()
        engine._agents = []
        engine._trading = MagicMock()
        engine._trading.get_balance = AsyncMock(
            return_value=MagicMock(total=10_000_000, available=9_000_000)
        )
        engine._recorder = MagicMock()
        engine._recorder.record_company_snapshot = AsyncMock()
        engine._recorder.commit = AsyncMock()
        engine._reconcile_with_broker = AsyncMock()

        await engine._run_cycle()

        engine._recorder.record_company_snapshot.assert_awaited_once()
        engine._reconcile_with_broker.assert_awaited_once()

    def test_guard_context_classifies_finance_first_failing_stage(self):
        engine = SimulationEngine()
        context = engine._classify_guard_context([
            {
                "agent_name": "Trader-Gamma",
                "finance_no_context": True,
                "first_failing_stage": "finance_tool_planner_model",
                "finance_record": {"failure_type": "sidecar_pipeline_failed"},
            }
        ])

        assert context["cause_classification"] == "finance_sidecar_no_context"
        assert context["first_failing_stage"] == "finance_tool_planner_model"
        assert context["failure_type"] == "sidecar_pipeline_failed"

    def test_guard_context_classifies_local_agent_timeout(self):
        engine = SimulationEngine()
        context = engine._classify_guard_context([
            {
                "agent_name": "CEO-Alpha",
                "errors": ["ReadTimeout"],
                "first_failing_stage": "local_agent_runtime_timeout",
            }
        ])

        assert context["cause_classification"] == "local_agent_runtime_failure"
        assert context["first_failing_stage"] == "local_agent_runtime_timeout"
        assert context["agent"] == "CEO-Alpha"

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
            mock_run.return_value = {"decisions": [], "emotion": {}, "next_cycle_seconds": 0}
            result = await engine._run_cycle()

        assert engine._cycle_count == 1
        assert mock_run.call_count == 2  # CEO + Analyst
        assert isinstance(result, int)

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
            mock_run.return_value = {"decisions": [], "emotion": {}, "next_cycle_seconds": 0}
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
    async def test_process_org_actions_any_agent_can_propose(self):
        """Any agent can propose org actions — not restricted to CEO."""
        engine = SimulationEngine()
        llm = _make_llm()

        analyst = AnalystAgent(profile=_make_profile("Analyst"), personality=create_random_personality(42), llm=llm)
        target = AnalystAgent(profile=_make_profile("BadAgent"), personality=create_random_personality(99), llm=llm)
        engine._agents = [analyst, target]

        result = {"decisions": [{"type": "fire", "target": "BadAgent", "reason": "underperforming"}]}
        await engine._process_org_actions(analyst, result)
        assert len(engine._agents) == 1
        assert engine._agents[0].name == "Analyst"

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
            mock_run.return_value = {"decisions": [], "emotion": {}, "next_cycle_seconds": 0}
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

    @pytest.mark.asyncio
    async def test_reconcile_with_broker_ok(self):
        """Reconciliation succeeds with no discrepancies when DB and broker match."""
        engine = SimulationEngine()
        llm = _make_llm()
        engine._llm = llm
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        engine._agents = [ceo]

        real_pos = MagicMock()
        real_pos.symbol = "005930"
        real_pos.quantity = 100
        real_pos.avg_price = 70000
        real_pos.unrealized_pnl = 5000
        real_pos.unrealized_pnl_pct = 0.07
        real_pos.market = "kr_stock"

        engine._trading = MagicMock()
        engine._trading.get_positions = AsyncMock(return_value=[real_pos])
        engine._trading.get_balance = AsyncMock(return_value=MagicMock(total=10_000_000))

        engine._recorder = MagicMock()
        engine._recorder.get_last_positions = AsyncMock(return_value=[
            {"symbol": "005930", "quantity": 100.0, "avg_price": 70000.0, "market": "kr_stock"}
        ])
        engine._recorder.get_position_owner = AsyncMock(return_value=ceo.agent_id)
        engine._recorder.record_position_snapshot = AsyncMock()
        engine._recorder.commit = AsyncMock()

        await engine._reconcile_with_broker()

        engine._recorder.record_position_snapshot.assert_called_once()
        engine._recorder.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_reconcile_with_broker_detects_discrepancy(self):
        """Reconciliation logs discrepancy when DB qty differs from broker."""
        engine = SimulationEngine()
        llm = _make_llm()
        engine._llm = llm
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        engine._agents = [ceo]

        real_pos = MagicMock()
        real_pos.symbol = "005930"
        real_pos.quantity = 100
        real_pos.avg_price = 70000
        real_pos.unrealized_pnl = 0
        real_pos.unrealized_pnl_pct = 0
        real_pos.market = "kr_stock"

        engine._trading = MagicMock()
        engine._trading.get_positions = AsyncMock(return_value=[real_pos])
        engine._trading.get_balance = AsyncMock(return_value=MagicMock(total=10_000_000))

        engine._recorder = MagicMock()
        engine._recorder.get_last_positions = AsyncMock(return_value=[
            {"symbol": "005930", "quantity": 50.0, "avg_price": 70000.0, "market": "kr_stock"}
        ])
        engine._recorder.get_position_owner = AsyncMock(return_value=ceo.agent_id)
        engine._recorder.record_position_snapshot = AsyncMock()
        engine._recorder.commit = AsyncMock()

        await engine._reconcile_with_broker()

        engine._recorder.record_position_snapshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_reconcile_assigns_last_trader_as_owner(self):
        """Position ownership is assigned to the agent who last traded that symbol."""
        engine = SimulationEngine()
        llm = _make_llm()
        engine._llm = llm
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        trader = AnalystAgent(profile=_make_profile("Trader-X"), personality=create_random_personality(99), llm=llm)
        engine._agents = [ceo, trader]

        real_pos = MagicMock()
        real_pos.symbol = "005930"
        real_pos.quantity = 10
        real_pos.avg_price = 70000
        real_pos.unrealized_pnl = 0
        real_pos.unrealized_pnl_pct = 0
        real_pos.market = "kr_stock"

        engine._trading = MagicMock()
        engine._trading.get_positions = AsyncMock(return_value=[real_pos])
        engine._trading.get_balance = AsyncMock(return_value=MagicMock(total=10_000_000))

        engine._recorder = MagicMock()
        engine._recorder.get_last_positions = AsyncMock(return_value=[])
        # Trader-X is the last trader for 005930
        engine._recorder.get_position_owner = AsyncMock(return_value=trader.agent_id)
        engine._recorder.record_position_snapshot = AsyncMock()
        engine._recorder.commit = AsyncMock()

        await engine._reconcile_with_broker()

        call_kwargs = engine._recorder.record_position_snapshot.call_args[1]
        assert call_kwargs["agent_id"] == trader.agent_id

    @pytest.mark.asyncio
    async def test_reconcile_reassigns_owner_when_trader_fired(self):
        """Orphan position (original trader fired) is reassigned to active agent."""
        engine = SimulationEngine()
        llm = _make_llm()
        engine._llm = llm
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        engine._agents = [ceo]  # only CEO active

        real_pos = MagicMock()
        real_pos.symbol = "005930"
        real_pos.quantity = 10
        real_pos.avg_price = 70000
        real_pos.unrealized_pnl = 0
        real_pos.unrealized_pnl_pct = 0
        real_pos.market = "kr_stock"

        engine._trading = MagicMock()
        engine._trading.get_positions = AsyncMock(return_value=[real_pos])
        engine._trading.get_balance = AsyncMock(return_value=MagicMock(total=10_000_000))

        engine._recorder = MagicMock()
        engine._recorder.get_last_positions = AsyncMock(return_value=[])
        # Original trader no longer active → get_position_owner returns None
        engine._recorder.get_position_owner = AsyncMock(return_value=None)
        engine._recorder.record_position_snapshot = AsyncMock()
        engine._recorder.commit = AsyncMock()

        await engine._reconcile_with_broker()

        # Fallback owner = CEO
        call_kwargs = engine._recorder.record_position_snapshot.call_args[1]
        assert call_kwargs["agent_id"] == ceo.agent_id

    @pytest.mark.asyncio
    async def test_reconcile_no_recorder_skips_gracefully(self):
        """Reconciliation skips when recorder is not initialized."""
        engine = SimulationEngine()
        engine._trading = MagicMock()
        engine._recorder = None  # No recorder

        # Should not raise
        await engine._reconcile_with_broker()

    @pytest.mark.asyncio
    async def test_reconcile_broker_error_handled(self):
        """Reconciliation handles broker errors without crashing."""
        engine = SimulationEngine()
        llm = _make_llm()
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        engine._agents = [ceo]
        engine._trading = MagicMock()
        engine._trading.get_positions = AsyncMock(side_effect=Exception("KIS timeout"))

        engine._recorder = MagicMock()
        engine._recorder.get_last_positions = AsyncMock(return_value=[])
        engine._recorder.commit = AsyncMock()

        # Should not raise
        await engine._reconcile_with_broker()

    @pytest.mark.asyncio
    async def test_hire_duplicate_name_gets_uuid_suffix(self):
        """Hiring an agent with a name that already exists renames with UUID suffix."""
        engine = SimulationEngine()
        llm = _make_llm()
        engine._llm = llm
        engine._trading = MagicMock()
        engine._market_data = MagicMock()

        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        existing = AnalystAgent(profile=_make_profile("RiskManager-Rho"), personality=create_random_personality(99), llm=llm)
        engine._agents = [ceo, existing]

        result = {
            "decisions": [{"type": "hire", "target": "RiskManager-Rho", "detail": "analyst", "reason": "retry"}],
        }

        with patch("agentic_capital.simulation.engine.create_agent") as mock_create:
            new_agent = AnalystAgent(profile=_make_profile("RiskManager-Rho-abcd1234"), personality=create_random_personality(77), llm=llm)
            mock_create.return_value = new_agent
            await engine._process_org_actions(ceo, result)

        assert len(engine._agents) == 3
        # create_agent should be called with renamed name (UUID suffix)
        call_kwargs = mock_create.call_args[1]
        hired_name = call_kwargs.get("name", mock_create.call_args[0][0] if mock_create.call_args[0] else "")
        assert hired_name != "RiskManager-Rho"
        assert "RiskManager-Rho-" in hired_name

    @pytest.mark.asyncio
    async def test_process_org_actions_skips_duplicate_hires_in_same_cycle(self):
        """Repeated identical hire decisions in one cycle create one agent."""
        engine = SimulationEngine()
        llm = _make_llm()
        engine._llm = llm
        engine._trading = MagicMock()

        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        engine._agents = [ceo]

        result = {
            "decisions": [
                {"type": "hire", "target": "TraderBeta", "detail": "trader", "reason": "add trader"},
                {"type": "hire", "target": "TraderBeta", "detail": "trader", "reason": "repeat"},
            ],
        }

        with patch("agentic_capital.simulation.engine.create_agent") as mock_create:
            new_agent = AnalystAgent(profile=_make_profile("TraderBeta"), personality=create_random_personality(77), llm=llm)
            mock_create.return_value = new_agent
            await engine._process_org_actions(ceo, result)

        mock_create.assert_called_once()
        assert len(engine._agents) == 2
