"""Unit tests for simulation recorder."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_capital.core.decision.pipeline import TradingDecision
from agentic_capital.core.personality.models import EmotionState, PersonalityVector
from agentic_capital.simulation.recorder import SimulationRecorder, _personality_to_dict, _emotion_to_dict


class TestPersonalityToDict:
    def test_converts_all_fields(self):
        p = PersonalityVector()
        d = _personality_to_dict(p)
        assert "openness" in d
        assert "loss_aversion" in d
        assert len(d) == 10

    def test_preserves_values(self):
        p = PersonalityVector(openness=0.8, loss_aversion=0.3)
        d = _personality_to_dict(p)
        assert d["openness"] == 0.8
        assert d["loss_aversion"] == 0.3


class TestEmotionToDict:
    def test_converts_all_fields(self):
        e = EmotionState()
        d = _emotion_to_dict(e)
        assert "valence" in d
        assert "stress" in d
        assert len(d) == 5


class TestSimulationRecorder:
    def _make_recorder(self):
        session = MagicMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.execute = AsyncMock()
        return SimulationRecorder(session)

    @pytest.mark.asyncio
    async def test_start_simulation(self):
        recorder = self._make_recorder()
        sim_id = await recorder.start_simulation(
            seed=42, initial_capital=10_000_000, config={"test": True}
        )
        assert sim_id is not None
        assert recorder._simulation_id is not None

    @pytest.mark.asyncio
    async def test_record_agent(self):
        recorder = self._make_recorder()
        recorder._simulation_id = uuid.uuid4()
        await recorder.record_agent(
            agent_id=uuid.uuid4(),
            name="Alpha",
            role="trader",
            philosophy="test",
            personality=PersonalityVector(),
        )
        # Two adds: AgentModel + AgentPersonalityModel
        assert recorder._session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_record_decision_hold(self):
        recorder = self._make_recorder()
        recorder._simulation_id = uuid.uuid4()
        d = TradingDecision("HOLD", "005930", 0, "waiting", 0.5)
        await recorder.record_decision(
            agent_id=uuid.uuid4(),
            decision=d,
            personality=PersonalityVector(),
            emotion=EmotionState(),
            status="executed",
        )
        # Only AgentDecisionModel (no TradeModel for HOLD)
        assert recorder._session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_record_decision_buy(self):
        recorder = self._make_recorder()
        recorder._simulation_id = uuid.uuid4()
        d = TradingDecision("BUY", "005930", 10, "bullish", 0.8)
        await recorder.record_decision(
            agent_id=uuid.uuid4(),
            decision=d,
            personality=PersonalityVector(),
            emotion=EmotionState(),
            status="submitted",
            price=70000,
        )
        # AgentDecisionModel + TradeModel
        assert recorder._session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_record_emotion(self):
        recorder = self._make_recorder()
        await recorder.record_emotion(
            agent_id=uuid.uuid4(),
            emotion=EmotionState(valence=0.5, stress=0.3),
            trigger="test",
        )
        assert recorder._session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_record_personality_drift(self):
        recorder = self._make_recorder()
        drifts = [("loss_aversion", 0.5, 0.52), ("openness", 0.5, 0.49)]
        await recorder.record_personality_drift(
            agent_id=uuid.uuid4(),
            drift_events=drifts,
            trigger="pnl",
        )
        assert recorder._session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_record_personality_drift_empty(self):
        recorder = self._make_recorder()
        await recorder.record_personality_drift(
            agent_id=uuid.uuid4(),
            drift_events=[],
        )
        assert recorder._session.add.call_count == 0

    @pytest.mark.asyncio
    async def test_record_company_snapshot(self):
        recorder = self._make_recorder()
        recorder._simulation_id = uuid.uuid4()
        await recorder.record_company_snapshot(
            total_capital=10_000_000,
            available_cash=8_000_000,
            agents_count=3,
        )
        assert recorder._session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_end_simulation(self):
        recorder = self._make_recorder()
        recorder._simulation_id = uuid.uuid4()
        await recorder.end_simulation("completed")
        assert recorder._session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_record_generic_decision(self):
        recorder = self._make_recorder()
        recorder._simulation_id = uuid.uuid4()
        await recorder.record_decision(
            agent_id=uuid.uuid4(),
            decision_type="strategy",
            action="focus on tech sector",
            reasoning="growth potential",
            confidence=0.7,
        )
        assert recorder._session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_record_hr_event(self):
        from agentic_capital.core.organization.hr import HREvent, HREventType
        recorder = self._make_recorder()
        recorder._simulation_id = uuid.uuid4()
        hr_event = HREvent(
            event_type=HREventType.FIRE,
            target_agent_id=uuid.uuid4(),
            decided_by=uuid.uuid4(),
            reasoning="poor performance",
            new_capital=0.0,
        )
        await recorder.record_hr_event(hr_event)
        assert recorder._session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_record_agent_message(self):
        from agentic_capital.core.communication.protocol import AgentMessage, MessageType
        recorder = self._make_recorder()
        recorder._simulation_id = uuid.uuid4()
        msg = AgentMessage(
            type=MessageType.SIGNAL,
            sender_id=uuid.uuid4(),
            content={"symbol": "005930", "signal": "BUY"},
        )
        await recorder.record_agent_message(msg)
        assert recorder._session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_record_position_snapshot(self):
        recorder = self._make_recorder()
        recorder._simulation_id = uuid.uuid4()
        await recorder.record_position_snapshot(
            agent_id=uuid.uuid4(),
            symbol="005930",
            quantity=100,
            avg_price=70000,
            unrealized_pnl=50000,
            unrealized_pnl_pct=0.71,
        )
        assert recorder._session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_record_role(self):
        recorder = self._make_recorder()
        recorder._simulation_id = uuid.uuid4()
        role_id = await recorder.record_role(
            role_name="risk_analyst",
            permissions=["read_positions", "send_signals"],
            created_by=uuid.uuid4(),
        )
        assert role_id is not None
        assert recorder._session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_record_permission_change(self):
        recorder = self._make_recorder()
        await recorder.record_permission_change(
            agent_id=uuid.uuid4(),
            action="grant",
            changes={"added": ["execute_trades"]},
            decided_by=uuid.uuid4(),
            reasoning="promoted to trader",
        )
        assert recorder._session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_record_agent_status_change(self):
        recorder = self._make_recorder()
        await recorder.record_agent_status_change(
            agent_id=uuid.uuid4(),
            new_status="fired",
            reason="CEO decision",
        )
        assert recorder._session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_record_company_snapshot_with_metrics(self):
        recorder = self._make_recorder()
        recorder._simulation_id = uuid.uuid4()
        await recorder.record_company_snapshot(
            total_capital=12_000_000,
            available_cash=5_000_000,
            agents_count=5,
            daily_pnl_pct=1.2,
            cumulative_pnl_pct=20.0,
            sharpe_30d=1.5,
            max_drawdown_pct=8.3,
            org_snapshot={"roles": ["ceo", "trader", "analyst"]},
        )
        assert recorder._session.add.call_count == 1

    @pytest.mark.asyncio
    async def test_commit(self):
        recorder = self._make_recorder()
        await recorder.commit()
        recorder._session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_tool_new(self):
        recorder = self._make_recorder()
        # First execute (SELECT) returns None → insert path
        # Second execute (flush) handled by flush mock
        recorder._session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
        )
        await recorder.save_tool(
            name="my_tool",
            description="A tool",
            code="async def my_tool() -> str: return 'hi'",
            created_by=uuid.uuid4(),
        )
        assert recorder._session.flush.called
        assert recorder._session.add.called

    @pytest.mark.asyncio
    async def test_save_tool_update_existing(self):
        recorder = self._make_recorder()
        existing = MagicMock()
        recorder._session.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=existing))
        )
        await recorder.save_tool(
            name="my_tool",
            description="Updated",
            code="async def my_tool() -> str: return 'updated'",
        )
        # execute called twice: SELECT + UPDATE
        assert recorder._session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_load_tools_returns_list(self):
        recorder = self._make_recorder()
        # Use PropertyMock-style object to avoid MagicMock name collision
        tool_mock = MagicMock()
        tool_mock.name = "calc_pnl"
        tool_mock.description = "Calc P&L"
        tool_mock.code = "async def calc_pnl() -> str: return 'pnl:0'"
        recorder._session.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[tool_mock]))))
        )
        tools = await recorder.load_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "calc_pnl"
        assert "code" in tools[0]
