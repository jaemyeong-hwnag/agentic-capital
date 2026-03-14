"""Unit tests for agent cycle workflow and recording."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agentic_capital.core.agents.base import AgentProfile
from agentic_capital.core.agents.ceo import CEOAgent
from agentic_capital.core.agents.analyst import AnalystAgent
from agentic_capital.core.agents.trader import TraderAgent
from agentic_capital.core.agents.factory import create_random_personality
from agentic_capital.graph.nodes import record_cycle
from agentic_capital.graph.state import AgentCycleResult, AgentWorkflowState
from agentic_capital.graph.workflow import run_agent_cycle
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
    md.get_quote = AsyncMock(return_value=MagicMock(
        price=70000, volume=5000000, bid=None, ask=None, market="kr_stock", currency="KRW",
    ))
    md.get_symbols = AsyncMock(return_value=["005930"])
    md.get_ohlcv = AsyncMock(return_value=[])
    md.get_order_book = AsyncMock(side_effect=NotImplementedError)
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


# ─── record_cycle tests ───


class TestRecordCycle:
    @pytest.mark.asyncio
    async def test_no_recorder_is_noop(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        # Should not raise
        await record_cycle(ceo, 1, decisions=[], messages=[], recorder=None)

    @pytest.mark.asyncio
    async def test_records_emotion(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        recorder = _make_recorder()
        await record_cycle(ceo, 1, decisions=[], messages=[], recorder=recorder)
        recorder.record_emotion.assert_called_once()
        recorder.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_records_trade_decision(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        recorder = _make_recorder()
        decisions = [{"type": "trade", "action": "BUY", "symbol": "005930", "quantity": 10, "reason": "strong", "confidence": 0.8}]
        await record_cycle(ceo, 1, decisions=decisions, messages=[], recorder=recorder)
        recorder.record_decision.assert_called_once()

    @pytest.mark.asyncio
    async def test_records_hr_decision(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        recorder = _make_recorder()
        target_id = str(uuid4())
        decisions = [{"type": "fire", "target": target_id, "reason": "poor performance", "confidence": 0.9}]
        await record_cycle(ceo, 1, decisions=decisions, messages=[], recorder=recorder)
        recorder.record_decision.assert_called_once()
        recorder.record_hr_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_records_general_decision(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        recorder = _make_recorder()
        decisions = [{"type": "strategy", "detail": "focus on tech", "reason": "growth"}]
        await record_cycle(ceo, 1, decisions=decisions, messages=[], recorder=recorder)
        recorder.record_decision.assert_called_once()

    @pytest.mark.asyncio
    async def test_records_messages(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        recorder = _make_recorder()
        messages = [{"type": "SIGNAL", "symbol": "005930", "content": {"signal": "BUY"}}]
        await record_cycle(ceo, 1, decisions=[], messages=messages, recorder=recorder)
        recorder.record_agent_message.assert_called_once()


# ─── AgentWorkflowState backward compat ───


class TestStateBackwardCompat:
    def test_agent_workflow_state_alias(self):
        """AgentWorkflowState must still be importable (backward compat)."""
        assert AgentWorkflowState is AgentCycleResult

    def test_can_create_state_dict(self):
        state: AgentWorkflowState = {
            "agent_id": str(uuid4()),
            "agent_name": "TestAgent",
            "cycle_number": 1,
            "decisions": [],
            "messages_to_send": [],
            "errors": [],
        }
        assert state["agent_name"] == "TestAgent"


# ─── run_agent_cycle tests (mocked LLM) ───


class TestRunAgentCycle:
    def _mock_react_result(self, decisions=None, messages=None):
        """Mock result from create_react_agent.ainvoke()."""
        from langchain_core.messages import AIMessage
        return {"messages": [AIMessage(content="Done.")]}

    @pytest.mark.asyncio
    async def test_full_cycle_ceo(self):
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=_make_llm())
        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(return_value=self._mock_react_result())

        with patch("agentic_capital.graph.workflow.create_react_agent", return_value=mock_agent), \
             patch("agentic_capital.graph.workflow._get_langchain_llm", return_value=MagicMock()):
            result = await run_agent_cycle(ceo, cycle_number=1)

        assert result["agent_name"] == "CEO"
        assert result["cycle_number"] == 1
        assert "decisions" in result
        assert "emotion" in result

    @pytest.mark.asyncio
    async def test_full_cycle_analyst(self):
        analyst = AnalystAgent(profile=_make_profile("Analyst"), personality=create_random_personality(42), llm=_make_llm())
        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(return_value=self._mock_react_result())

        with patch("agentic_capital.graph.workflow.create_react_agent", return_value=mock_agent), \
             patch("agentic_capital.graph.workflow._get_langchain_llm", return_value=MagicMock()):
            result = await run_agent_cycle(
                analyst, cycle_number=1,
                symbols=["005930"],
            )

        assert result["agent_name"] == "Analyst"
        assert "emotion" in result

    @pytest.mark.asyncio
    async def test_full_cycle_trader(self):
        trading = _make_trading()

        trader = TraderAgent(
            profile=_make_profile("Trader"),
            personality=create_random_personality(42),
            llm=_make_llm(), trading=trading,
        )
        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(return_value=self._mock_react_result())

        with patch("agentic_capital.graph.workflow.create_react_agent", return_value=mock_agent), \
             patch("agentic_capital.graph.workflow._get_langchain_llm", return_value=MagicMock()):
            result = await run_agent_cycle(
                trader, cycle_number=1,
                trading=trading,
                symbols=["005930"],
            )

        assert result["agent_name"] == "Trader"

    @pytest.mark.asyncio
    async def test_handles_react_failure_gracefully(self):
        """If ReAct agent throws, cycle still returns with errors."""
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=_make_llm())
        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(side_effect=RuntimeError("LLM quota exceeded"))

        with patch("agentic_capital.graph.workflow.create_react_agent", return_value=mock_agent), \
             patch("agentic_capital.graph.workflow._get_langchain_llm", return_value=MagicMock()):
            result = await run_agent_cycle(ceo, cycle_number=1)

        assert result["agent_name"] == "CEO"
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_extracts_org_decisions_from_message(self):
        """JSON org decisions in LLM output are parsed and included."""
        from langchain_core.messages import AIMessage
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=_make_llm())
        hire_json = '[{"type": "hire", "role": "analyst", "target": "Analyst-2", "reason": "need more coverage"}]'
        mock_react_result = {"messages": [AIMessage(content=f"I'll hire a new analyst.\n```json\n{hire_json}\n```")]}

        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(return_value=mock_react_result)

        with patch("agentic_capital.graph.workflow.create_react_agent", return_value=mock_agent), \
             patch("agentic_capital.graph.workflow._get_langchain_llm", return_value=MagicMock()):
            result = await run_agent_cycle(ceo, cycle_number=1)

        org_decisions = [d for d in result["decisions"] if d.get("type") == "hire"]
        assert len(org_decisions) == 1
        assert org_decisions[0]["role"] == "analyst"
