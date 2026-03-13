"""Unit tests for decision pipeline and reflection."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agentic_capital.core.decision.pipeline import DecisionPipeline, TradingDecision
from agentic_capital.core.decision.reflection import reflect_on_trades
from agentic_capital.core.personality.models import EmotionState, PersonalityVector
from agentic_capital.ports.market_data import Quote
from agentic_capital.ports.trading import Balance, OrderResult, OrderSide, Position


class TestTradingDecision:
    def test_create(self):
        d = TradingDecision("BUY", "005930", 10, "bullish", 0.8)
        assert d.action == "BUY"
        assert d.symbol == "005930"
        assert d.quantity == 10
        assert d.confidence == 0.8


class TestDecisionPipeline:
    def _make_pipeline(self):
        llm = MagicMock()
        trading = MagicMock()
        market_data = MagicMock()
        return DecisionPipeline(llm=llm, trading=trading, market_data=market_data)

    @pytest.mark.asyncio
    async def test_collect_market_data(self):
        pipeline = self._make_pipeline()
        mock_quote = Quote(symbol="005930", price=72000, volume=5000000)
        pipeline._market_data.get_quote = AsyncMock(return_value=mock_quote)

        data = await pipeline._collect_market_data(["005930"])
        assert len(data) == 1
        assert data[0]["price"] == 72000

    @pytest.mark.asyncio
    async def test_collect_market_data_failure(self):
        pipeline = self._make_pipeline()
        pipeline._market_data.get_quote = AsyncMock(side_effect=RuntimeError("fail"))

        data = await pipeline._collect_market_data(["005930"])
        assert data == []

    @pytest.mark.asyncio
    async def test_get_llm_decisions_valid(self):
        pipeline = self._make_pipeline()
        pipeline._llm.generate = AsyncMock(return_value='{"decisions": [{"action": "BUY", "symbol": "005930", "quantity": 10, "reason": "bullish"}], "confidence": 0.8}')

        decisions = await pipeline._get_llm_decisions("system", "prompt", "Alpha")
        assert len(decisions) == 1
        assert decisions[0].action == "BUY"
        assert decisions[0].quantity == 10

    @pytest.mark.asyncio
    async def test_get_llm_decisions_code_block(self):
        pipeline = self._make_pipeline()
        pipeline._llm.generate = AsyncMock(return_value='```json\n{"decisions": [{"action": "SELL", "symbol": "005930", "quantity": 5, "reason": "bearish"}], "confidence": 0.6}\n```')

        decisions = await pipeline._get_llm_decisions("system", "prompt", "Beta")
        assert len(decisions) == 1
        assert decisions[0].action == "SELL"

    @pytest.mark.asyncio
    async def test_get_llm_decisions_invalid_json(self):
        pipeline = self._make_pipeline()
        pipeline._llm.generate = AsyncMock(return_value="not json")

        decisions = await pipeline._get_llm_decisions("system", "prompt", "Gamma")
        assert decisions == []

    @pytest.mark.asyncio
    async def test_execute_decision_buy(self):
        pipeline = self._make_pipeline()
        pipeline._market_data.get_quote = AsyncMock(
            return_value=Quote(symbol="005930", price=70000)
        )
        pipeline._trading.submit_order = AsyncMock(
            return_value=OrderResult(
                order_id="1", symbol="005930", side=OrderSide.BUY,
                quantity=10, filled_price=70000, status="submitted"
            )
        )

        d = TradingDecision("BUY", "005930", 10, "test", 0.8)
        success = await pipeline._execute_decision(d, 1_000_000, "Alpha")
        assert success is True

    @pytest.mark.asyncio
    async def test_execute_decision_insufficient_capital(self):
        pipeline = self._make_pipeline()
        pipeline._market_data.get_quote = AsyncMock(
            return_value=Quote(symbol="005930", price=70000)
        )
        pipeline._trading.submit_order = AsyncMock(
            return_value=OrderResult(
                order_id="1", symbol="005930", side=OrderSide.BUY,
                quantity=1, filled_price=70000, status="submitted"
            )
        )

        d = TradingDecision("BUY", "005930", 100, "test", 0.8)
        success = await pipeline._execute_decision(d, 100_000, "Alpha")
        # 100 * 70000 = 7M > 100K, adjusted to max_qty = 1
        assert success is True
        assert d.quantity == 1

    @pytest.mark.asyncio
    async def test_execute_decision_zero_quantity(self):
        pipeline = self._make_pipeline()
        d = TradingDecision("BUY", "005930", 0, "test", 0.8)
        success = await pipeline._execute_decision(d, 1_000_000, "Alpha")
        assert success is False

    @pytest.mark.asyncio
    async def test_run_cycle_no_system_enforced_emotion(self):
        """Pipeline returns emotion unchanged — no system-enforced emotion update."""
        pipeline = self._make_pipeline()

        pipeline._market_data.get_quote = AsyncMock(
            return_value=Quote(symbol="005930", price=70000, volume=5000000)
        )
        pipeline._trading.get_balance = AsyncMock(
            return_value=Balance(total=10_000_000, available=10_000_000, currency="KRW")
        )
        pipeline._trading.get_positions = AsyncMock(return_value=[])
        pipeline._llm.generate = AsyncMock(
            return_value='{"decisions": [{"action": "HOLD", "symbol": "005930", "quantity": 0, "reason": "waiting"}], "confidence": 0.5}'
        )

        original_emotion = EmotionState(valence=0.3, stress=0.4, confidence=0.6)
        decisions, emotion = await pipeline.run_cycle(
            agent_name="Alpha",
            agent_role="trader",
            philosophy="test",
            personality=PersonalityVector(),
            emotion=original_emotion,
            symbols=["005930"],
        )
        # Emotion returned unchanged — no system-enforced formula
        assert emotion.valence == original_emotion.valence
        assert emotion.stress == original_emotion.stress
        assert emotion.confidence == original_emotion.confidence


class TestReflection:
    def test_no_decisions(self):
        p = PersonalityVector(loss_aversion=0.5)
        updated, events = reflect_on_trades(p, [], -5.0)
        assert updated == p
        assert events == []

    def test_no_system_enforced_drift_on_loss(self):
        """Significant loss should NOT trigger system-enforced personality drift."""
        p = PersonalityVector(loss_aversion=0.5, conscientiousness=0.5)
        decisions = [TradingDecision("BUY", "005930", 10, "test")]
        updated, events = reflect_on_trades(p, decisions, -3.0)
        # No drift — agent decides autonomously
        assert updated.loss_aversion == 0.5
        assert updated.conscientiousness == 0.5
        assert events == []

    def test_no_system_enforced_drift_on_gain(self):
        """Significant gain should NOT trigger system-enforced personality drift."""
        p = PersonalityVector(loss_aversion=0.5, openness=0.5)
        decisions = [TradingDecision("SELL", "005930", 10, "test")]
        updated, events = reflect_on_trades(p, decisions, 4.0)
        # No drift — agent decides autonomously
        assert updated.loss_aversion == 0.5
        assert updated.openness == 0.5
        assert events == []

    def test_minor_change_no_drift(self):
        p = PersonalityVector(loss_aversion=0.5)
        decisions = [TradingDecision("BUY", "005930", 10, "test")]
        updated, events = reflect_on_trades(p, decisions, 0.5)
        assert updated == p
        assert events == []
