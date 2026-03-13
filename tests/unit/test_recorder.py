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
    async def test_commit(self):
        recorder = self._make_recorder()
        await recorder.commit()
        recorder._session.commit.assert_called_once()
