"""Unit tests for CEO, Analyst, and Trader agents."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agentic_capital.core.agents.analyst import AnalystAgent, AnalystSignal
from agentic_capital.core.agents.base import AgentProfile
from agentic_capital.core.agents.ceo import CEOAction, CEOAgent
from agentic_capital.core.agents.factory import create_agent, create_random_personality
from agentic_capital.core.agents.trader import TraderAgent
from agentic_capital.core.communication.protocol import MessageType
from agentic_capital.core.organization.hr import HREventType
from agentic_capital.core.personality.models import EmotionState, PersonalityVector


def _make_profile(name: str = "TestAgent") -> AgentProfile:
    return AgentProfile(id=uuid4(), name=name, philosophy="test philosophy")


def _make_personality() -> PersonalityVector:
    return create_random_personality(seed=42)


def _make_llm(response: str = '{"actions": [], "confidence": 0.5}') -> MagicMock:
    from agentic_capital.ports.llm import LLMPort
    llm = MagicMock(spec=LLMPort)
    llm.generate = AsyncMock(return_value=response)
    llm.embed = AsyncMock(return_value=[0.0] * 1024)
    return llm


# ─── CEO Agent ───


class TestCEOAgent:
    def test_create(self):
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=_make_personality(), llm=_make_llm())
        assert ceo.name == "CEO"
        assert ceo.emotion.valence == 0.0

    @pytest.mark.asyncio
    async def test_think_no_actions(self):
        llm = _make_llm('{"actions": [], "strategy_update": "hold steady", "confidence": 0.6}')
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=_make_personality(), llm=llm)
        result = await ceo.think({
            "agents": [],
            "company_state": {"total_capital": 10_000_000, "total_agents": 3},
            "recent_performance": [],
        })
        assert result["actions"] == []
        llm.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_think_with_hire_action(self):
        response = '{"actions": [{"type": "hire", "target": "new analyst", "detail": "tech sector focus", "reason": "need more coverage"}], "confidence": 0.8}'
        llm = _make_llm(response)
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=_make_personality(), llm=llm)
        result = await ceo.think({
            "agents": [{"name": "Alpha", "role": "trader", "capital": 5_000_000, "pnl_pct": 2.1}],
            "company_state": {"total_capital": 10_000_000, "total_agents": 1},
            "recent_performance": [],
        })
        actions = result["actions"]
        assert len(actions) == 1
        assert actions[0].action_type == "hire"
        assert actions[0].target == "new analyst"

    @pytest.mark.asyncio
    async def test_think_handles_invalid_json(self):
        llm = _make_llm("this is not json")
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=_make_personality(), llm=llm)
        result = await ceo.think({"agents": [], "company_state": {}, "recent_performance": []})
        assert result["actions"] == []

    @pytest.mark.asyncio
    async def test_reflect_no_system_enforced_drift(self):
        """Reflect should NOT system-enforce any personality changes."""
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=_make_personality(), llm=_make_llm())
        original = ceo.personality.conscientiousness
        await ceo.reflect({"pnl_pct": -5.0})
        # No system-enforced drift — agent decides autonomously
        assert ceo.personality.conscientiousness == original

    def test_action_to_hr_event(self):
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=_make_personality(), llm=_make_llm())
        action = CEOAction(action_type="fire", target="Alpha", reason="underperformance")
        target_id = uuid4()
        event = ceo.action_to_hr_event(action, target_id)
        assert event is not None
        assert event.event_type == HREventType.FIRE
        assert event.decided_by == ceo.agent_id
        assert event.reasoning == "underperformance"

    def test_action_to_hr_event_invalid_target(self):
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=_make_personality(), llm=_make_llm())
        action = CEOAction(action_type="fire", target="Alpha", reason="test")
        event = ceo.action_to_hr_event(action, "not-a-uuid")
        assert event is None

    def test_action_to_hr_event_strategy_type(self):
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=_make_personality(), llm=_make_llm())
        action = CEOAction(action_type="strategy", target="all", reason="pivot to tech")
        event = ceo.action_to_hr_event(action, uuid4())
        assert event is None  # strategy is not an HR event


# ─── Analyst Agent ───


class TestAnalystAgent:
    def test_create(self):
        analyst = AnalystAgent(profile=_make_profile("Analyst"), personality=_make_personality(), llm=_make_llm())
        assert analyst.name == "Analyst"

    @pytest.mark.asyncio
    async def test_think_generates_signals(self):
        response = '{"signals": [{"symbol": "005930", "signal": "BUY", "confidence": 0.8, "thesis": "strong fundamentals"}], "market_outlook": "bullish"}'
        llm = _make_llm(response)
        analyst = AnalystAgent(profile=_make_profile("Analyst"), personality=_make_personality(), llm=llm)
        result = await analyst.think({
            "market_data": [{"symbol": "005930", "price": 70000, "change_pct": 1.5, "volume": 10000000}],
        })
        signals = result["signals"]
        assert len(signals) == 1
        assert signals[0].symbol == "005930"
        assert signals[0].signal == "BUY"
        assert signals[0].confidence == 0.8

    @pytest.mark.asyncio
    async def test_think_no_signals(self):
        llm = _make_llm('{"signals": [], "market_outlook": "uncertain"}')
        analyst = AnalystAgent(profile=_make_profile("Analyst"), personality=_make_personality(), llm=llm)
        result = await analyst.think({"market_data": []})
        assert result["signals"] == []

    @pytest.mark.asyncio
    async def test_think_handles_invalid_json(self):
        llm = _make_llm("broken json")
        analyst = AnalystAgent(profile=_make_profile("Analyst"), personality=_make_personality(), llm=llm)
        result = await analyst.think({"market_data": []})
        assert result["signals"] == []

    @pytest.mark.asyncio
    async def test_reflect_no_system_enforced_drift(self):
        """Reflect should NOT system-enforce any personality changes."""
        analyst = AnalystAgent(profile=_make_profile("Analyst"), personality=_make_personality(), llm=_make_llm())
        original_c = analyst.personality.conscientiousness
        original_o = analyst.personality.openness
        await analyst.reflect({"signal_accuracy": 0.2})
        # No system-enforced drift
        assert analyst.personality.conscientiousness == original_c
        assert analyst.personality.openness == original_o

    def test_signal_to_message(self):
        analyst = AnalystAgent(profile=_make_profile("Analyst"), personality=_make_personality(), llm=_make_llm())
        signal = AnalystSignal(symbol="005930", signal="BUY", confidence=0.75, thesis="test thesis")
        msg = analyst.signal_to_message(signal)
        assert msg.type == MessageType.SIGNAL
        assert msg.sender_id == analyst.agent_id
        assert msg.priority == 0.75
        assert msg.content["signal"] == "BUY"

    def test_signal_to_message_with_receiver(self):
        analyst = AnalystAgent(profile=_make_profile("Analyst"), personality=_make_personality(), llm=_make_llm())
        signal = AnalystSignal(symbol="005930", signal="SELL", confidence=0.6, thesis="overbought")
        receiver = uuid4()
        msg = analyst.signal_to_message(signal, receiver_id=receiver)
        assert msg.receiver_id == receiver


# ─── Trader Agent ───


class TestTraderAgent:
    def _make_trader(self):
        llm = _make_llm('{"decisions": [], "market_outlook": "neutral", "confidence": 0.5}')
        trading = MagicMock()
        trading.get_balance = AsyncMock(return_value=MagicMock(total=10_000_000, available=10_000_000))
        trading.get_positions = AsyncMock(return_value=[])
        return TraderAgent(
            profile=_make_profile("Trader"),
            personality=_make_personality(),
            llm=llm, trading=trading,
        )

    def test_create(self):
        trader = self._make_trader()
        assert trader.name == "Trader"

    @pytest.mark.asyncio
    async def test_think_no_decisions(self):
        trader = self._make_trader()
        result = await trader.think({"symbols": ["005930"]})
        assert result["decisions"] == []
        assert result["updated_emotion"] is not None

    @pytest.mark.asyncio
    async def test_reflect_no_system_enforced_drift(self):
        """Reflect should NOT system-enforce any personality or emotion changes."""
        trader = self._make_trader()
        original_la = trader.personality.loss_aversion
        original_valence = trader.emotion.valence
        await trader.reflect({"pnl_pct": -3.0})
        # No system-enforced drift or emotion formula
        assert trader.personality.loss_aversion == original_la
        assert trader.emotion.valence == original_valence


# ─── Factory ───


class TestCreateAgent:
    def test_create_ceo(self):
        agent = create_agent("ceo", "CEO", llm=_make_llm())
        assert isinstance(agent, CEOAgent)
        assert agent.name == "CEO"

    def test_create_analyst(self):
        agent = create_agent("analyst", "Analyst", llm=_make_llm())
        assert isinstance(agent, AnalystAgent)

    def test_create_trader(self):
        from agentic_capital.ports.trading import TradingPort

        trading = MagicMock(spec=TradingPort)
        agent = create_agent("trader", "Trader", llm=_make_llm(), trading=trading)
        assert isinstance(agent, TraderAgent)

    def test_create_custom_role_creates_analyst(self):
        """Any custom role name creates an AnalystAgent — no restrictions."""
        from agentic_capital.core.agents.analyst import AnalystAgent
        agent = create_agent("janitor", "Bob", llm=_make_llm())
        assert isinstance(agent, AnalystAgent)
        assert agent.name == "Bob"

    def test_create_without_llm(self):
        with pytest.raises(TypeError, match="llm must be"):
            create_agent("ceo", "CEO")

    def test_create_with_custom_personality(self):
        p = PersonalityVector(openness=0.9, loss_aversion=0.1)
        agent = create_agent("analyst", "Custom", personality=p, llm=_make_llm())
        assert agent.personality.openness == 0.9
        assert agent.personality.loss_aversion == 0.1

    def test_create_with_seed(self):
        a1 = create_agent("analyst", "A1", seed=42, llm=_make_llm())
        a2 = create_agent("analyst", "A2", seed=42, llm=_make_llm())
        assert a1.personality.openness == a2.personality.openness
