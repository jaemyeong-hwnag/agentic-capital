"""Unit tests for LangGraph workflow."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agentic_capital.core.agents.base import AgentProfile
from agentic_capital.core.agents.ceo import CEOAgent
from agentic_capital.core.agents.analyst import AnalystAgent
from agentic_capital.core.agents.trader import TraderAgent
from agentic_capital.core.agents.factory import create_random_personality
from agentic_capital.core.personality.models import PersonalityVector
from agentic_capital.graph.nodes import gather_data, think, reflect, record
from agentic_capital.graph.state import AgentWorkflowState
from agentic_capital.graph.workflow import build_agent_workflow, run_agent_cycle
from agentic_capital.ports.llm import LLMPort


def _make_profile(name="Test"):
    return AgentProfile(id=uuid4(), name=name, philosophy="test")


def _make_llm(response='{"actions": [], "confidence": 0.5}'):
    llm = MagicMock(spec=LLMPort)
    llm.generate = AsyncMock(return_value=response)
    llm.embed = AsyncMock(return_value=[0.0] * 1024)
    return llm


def _make_trading():
    trading = MagicMock()
    trading.get_balance = AsyncMock(return_value=MagicMock(total=10_000_000, available=10_000_000, currency="KRW"))
    trading.get_positions = AsyncMock(return_value=[])
    trading.submit_order = AsyncMock()
    return trading


def _make_market_data():
    md = MagicMock()
    md.get_quote = AsyncMock(return_value=MagicMock(price=70000, volume=5000000))
    md.get_symbols = AsyncMock(return_value=["005930"])
    return md


def _make_state(**overrides) -> AgentWorkflowState:
    state: AgentWorkflowState = {
        "agent_id": str(uuid4()),
        "agent_name": "TestAgent",
        "agent_role": "trader",
        "cycle_number": 1,
        "market_data": [],
        "balance": {},
        "positions": [],
        "decisions": [],
        "messages_to_send": [],
        "errors": [],
    }
    state.update(overrides)
    return state


# ─── Node Tests ───


class TestGatherDataNode:
    @pytest.mark.asyncio
    async def test_gathers_balance_and_positions(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        trading = _make_trading()
        state = _make_state()
        result = await gather_data(state, ceo, trading=trading)
        assert "balance" in result
        assert result["balance"]["total"] == 10_000_000

    @pytest.mark.asyncio
    async def test_gathers_market_data(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        md = _make_market_data()
        state = _make_state()
        result = await gather_data(state, ceo, market_data=md, symbols=["005930"])
        assert len(result.get("market_data", [])) == 1
        assert result["market_data"][0]["price"] == 70000

    @pytest.mark.asyncio
    async def test_handles_no_deps(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        state = _make_state()
        result = await gather_data(state, ceo)
        assert result.get("errors") is None or result.get("errors") == []


class TestThinkNode:
    @pytest.mark.asyncio
    async def test_ceo_think(self):
        llm = _make_llm('{"actions": [{"type": "strategy", "target": "all", "detail": "focus tech", "reason": "growth"}], "confidence": 0.7}')
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        state = _make_state(agent_name="CEO")
        result = await think(state, ceo)
        assert len(result.get("decisions", [])) == 1

    @pytest.mark.asyncio
    async def test_analyst_think(self):
        llm = _make_llm('{"signals": [{"symbol": "005930", "signal": "BUY", "confidence": 0.8, "thesis": "strong"}], "market_outlook": "bullish"}')
        analyst = AnalystAgent(profile=_make_profile("Analyst"), personality=create_random_personality(42), llm=llm)
        state = _make_state(agent_name="Analyst", market_data=[{"symbol": "005930", "price": 70000}])
        result = await think(state, analyst)
        assert len(result.get("decisions", [])) > 0 or len(result.get("messages_to_send", [])) > 0

    @pytest.mark.asyncio
    async def test_handles_llm_failure(self):
        llm = _make_llm("not json at all")
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=llm)
        state = _make_state()
        result = await think(state, ceo)
        assert result["decisions"] == []


class TestReflectNode:
    @pytest.mark.asyncio
    async def test_updates_emotion(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        state = _make_state(positions=[{"unrealized_pnl_pct": 5.0}])
        result = await reflect(state, ceo)
        assert "emotion" in result
        assert "valence" in result["emotion"]

    @pytest.mark.asyncio
    async def test_handles_no_positions(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        state = _make_state(positions=[])
        result = await reflect(state, ceo)
        assert "emotion" in result


class TestRecordNode:
    @pytest.mark.asyncio
    async def test_no_recorder_is_noop(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        state = _make_state()
        result = await record(state, ceo)
        assert result == {}

    @pytest.mark.asyncio
    async def test_records_with_recorder(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        recorder = MagicMock()
        recorder.record_emotion = AsyncMock()
        recorder.record_decision = AsyncMock()
        recorder.commit = AsyncMock()
        state = _make_state(agent_id=str(ceo.agent_id))
        result = await record(state, ceo, recorder=recorder)
        recorder.record_emotion.assert_called_once()
        recorder.commit.assert_called_once()


# ─── Workflow Tests ───


class TestBuildAgentWorkflow:
    def test_builds_graph(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        graph = build_agent_workflow(ceo)
        assert graph is not None

    def test_builds_with_deps(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        graph = build_agent_workflow(
            ceo,
            trading=_make_trading(),
            market_data=_make_market_data(),
            symbols=["005930"],
        )
        assert graph is not None


class TestRunAgentCycle:
    @pytest.mark.asyncio
    async def test_full_cycle_ceo(self):
        llm = _make_llm('{"actions": [], "confidence": 0.5}')
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm)
        result = await run_agent_cycle(ceo, cycle_number=1)
        assert result["agent_name"] == "CEO"
        assert result["cycle_number"] == 1
        assert "decisions" in result
        assert "emotion" in result

    @pytest.mark.asyncio
    async def test_full_cycle_analyst(self):
        llm = _make_llm('{"signals": [], "market_outlook": "neutral"}')
        analyst = AnalystAgent(profile=_make_profile("Analyst"), personality=create_random_personality(42), llm=llm)
        result = await run_agent_cycle(
            analyst, cycle_number=1,
            market_data=_make_market_data(),
            symbols=["005930"],
        )
        assert result["agent_name"] == "Analyst"
        assert "emotion" in result

    @pytest.mark.asyncio
    async def test_full_cycle_trader(self):
        llm = _make_llm('{"decisions": [], "market_outlook": "neutral", "confidence": 0.5}')
        from agentic_capital.ports.trading import TradingPort
        from agentic_capital.ports.market_data import MarketDataPort
        trading = MagicMock(spec=TradingPort)
        trading.get_balance = AsyncMock(return_value=MagicMock(total=10_000_000, available=10_000_000, currency="KRW"))
        trading.get_positions = AsyncMock(return_value=[])
        md = MagicMock(spec=MarketDataPort)
        md.get_quote = AsyncMock(return_value=MagicMock(price=70000, volume=5000000))

        trader = TraderAgent(
            profile=_make_profile("Trader"),
            personality=create_random_personality(42),
            llm=llm, trading=trading, market_data=md,
        )
        result = await run_agent_cycle(
            trader, cycle_number=1,
            trading=trading, market_data=md,
            symbols=["005930"],
        )
        assert result["agent_name"] == "Trader"
