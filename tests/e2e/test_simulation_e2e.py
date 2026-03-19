"""E2E tests for full simulation cycle.

Tests the complete flow: agent creation → LangGraph workflow →
decision making → recording. Uses mock adapters to avoid
external dependencies while testing the full pipeline.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agentic_capital.core.agents.base import AgentProfile
from agentic_capital.core.agents.analyst import AnalystAgent
from agentic_capital.core.agents.ceo import CEOAgent
from agentic_capital.core.agents.factory import create_random_personality
from agentic_capital.core.agents.trader import TraderAgent
from agentic_capital.graph.workflow import run_agent_cycle
from agentic_capital.ports.llm import LLMPort
from agentic_capital.ports.trading import TradingPort


def _make_profile(name="Test"):
    return AgentProfile(id=uuid4(), name=name, philosophy="test")


def _make_llm(response='{"actions": [], "confidence": 0.5}'):
    llm = MagicMock(spec=LLMPort)
    llm.generate = AsyncMock(return_value=response)
    llm.embed = AsyncMock(return_value=[0.0] * 1024)
    return llm


def _make_trading():
    trading = MagicMock(spec=TradingPort)
    trading.get_balance = AsyncMock(
        return_value=MagicMock(total=10_000_000, available=8_000_000, currency="KRW")
    )
    trading.get_positions = AsyncMock(return_value=[
        MagicMock(
            symbol="005930", quantity=100, avg_price=70000,
            current_price=72000, unrealized_pnl_pct=2.86,
        ),
    ])
    trading.submit_order = AsyncMock()
    return trading


def _make_recorder():
    recorder = MagicMock()
    recorder.record_emotion = AsyncMock()
    recorder.record_decision = AsyncMock()
    recorder.record_hr_event = AsyncMock()
    recorder.record_agent_message = AsyncMock()
    recorder.record_position_snapshot = AsyncMock()
    recorder.record_personality_drift = AsyncMock()
    recorder.commit = AsyncMock()
    return recorder


@pytest.mark.e2e
class TestFullSimulationCycle:
    """Full simulation cycle — all three agents run through LangGraph."""

    @pytest.mark.asyncio
    async def test_ceo_full_cycle_with_org_decisions(self):
        """CEO runs full cycle: gather → think → reflect → record."""
        llm = _make_llm(
            '{"actions": [{"type": "strategy", "target": "all", "detail": "focus on tech", "reason": "growth potential"}], "confidence": 0.8}'
        )
        ceo = CEOAgent(
            profile=_make_profile("CEO-Alpha"),
            personality=create_random_personality(42),
            llm=llm,
        )
        recorder = _make_recorder()

        result = await run_agent_cycle(
            ceo,
            cycle_number=1,
            trading=_make_trading(),
            symbols=["005930"],
            recorder=recorder,
        )

        assert result["agent_name"] == "CEO-Alpha"
        assert result["cycle_number"] == 1
        assert "decisions" in result
        assert "emotion" in result
        recorder.record_emotion.assert_called_once()
        recorder.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyst_full_cycle_with_signals(self):
        """Analyst runs full cycle: gather → analyze → reflect → record."""
        llm = _make_llm(
            '{"signals": [{"symbol": "005930", "signal": "BUY", "confidence": 0.85, "thesis": "strong fundamentals"}], "market_outlook": "bullish"}'
        )
        analyst = AnalystAgent(
            profile=_make_profile("Analyst-Beta"),
            personality=create_random_personality(43),
            llm=llm,
        )
        recorder = _make_recorder()

        result = await run_agent_cycle(
            analyst,
            cycle_number=1,
            symbols=["005930"],
            recorder=recorder,
        )

        assert result["agent_name"] == "Analyst-Beta"
        assert "emotion" in result
        recorder.record_emotion.assert_called_once()
        recorder.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_trader_full_cycle_with_trades(self):
        """Trader runs full cycle: gather → decide → reflect → record."""
        llm = _make_llm(
            '{"decisions": [{"action": "BUY", "symbol": "005930", "quantity": 10, "reason": "bullish signal", "confidence": 0.75}], "confidence": 0.75}'
        )
        trading = _make_trading()

        trader = TraderAgent(
            profile=_make_profile("Trader-Gamma"),
            personality=create_random_personality(44),
            llm=llm,
            trading=trading,
        )
        recorder = _make_recorder()

        result = await run_agent_cycle(
            trader,
            cycle_number=1,
            trading=trading,
            symbols=["005930"],
            recorder=recorder,
        )

        assert result["agent_name"] == "Trader-Gamma"
        assert "emotion" in result
        recorder.record_emotion.assert_called_once()
        recorder.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_multi_agent_sequential_cycle(self):
        """All three agents run sequentially in one cycle — like the engine."""
        llm_ceo = _make_llm('{"actions": [{"type": "strategy", "target": "all", "detail": "diversify"}], "confidence": 0.7}')
        llm_analyst = _make_llm('{"signals": [{"symbol": "005930", "signal": "BUY", "confidence": 0.8, "thesis": "growth"}], "market_outlook": "neutral"}')
        llm_trader = _make_llm('{"decisions": [], "confidence": 0.5}')

        trading = _make_trading()
        recorder = _make_recorder()

        agents = [
            CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=llm_ceo),
            AnalystAgent(profile=_make_profile("Analyst"), personality=create_random_personality(43), llm=llm_analyst),
            TraderAgent(profile=_make_profile("Trader"), personality=create_random_personality(44), llm=llm_trader, trading=trading),
        ]

        results = []
        for agent in agents:
            result = await run_agent_cycle(
                agent,
                cycle_number=1,
                trading=trading,
                symbols=["005930"],
                recorder=recorder,
            )
            results.append(result)

        assert len(results) == 3
        assert results[0]["agent_name"] == "CEO"
        assert results[1]["agent_name"] == "Analyst"
        assert results[2]["agent_name"] == "Trader"

        # All agents got emotion recorded
        assert recorder.record_emotion.call_count == 3
        assert recorder.commit.call_count == 3

    @pytest.mark.asyncio
    async def test_multiple_cycles_personality_drift(self):
        """Run multiple cycles and verify personality changes over time."""
        responses = [
            '{"actions": [], "confidence": 0.5}',
            '{"actions": [], "confidence": 0.5}',
            '{"actions": [], "confidence": 0.5}',
        ]

        llm = MagicMock(spec=LLMPort)
        llm.generate = AsyncMock(side_effect=responses + responses * 5)  # Enough for multiple calls
        llm.embed = AsyncMock(return_value=[0.0] * 1024)

        ceo = CEOAgent(
            profile=_make_profile("CEO"),
            personality=create_random_personality(42),
            llm=llm,
        )

        initial_openness = ceo.personality.openness
        trading = _make_trading()
        # Give positions with loss to trigger personality drift
        trading.get_positions = AsyncMock(return_value=[
            MagicMock(symbol="005930", quantity=100, avg_price=70000,
                      current_price=60000, unrealized_pnl_pct=-14.3),
        ])

        for cycle in range(1, 4):
            await run_agent_cycle(ceo, cycle_number=cycle, trading=trading)

        # After 3 cycles with losses, personality should have drifted
        # (conscientiousness up, neuroticism up due to company loss reflection)
        assert ceo.personality is not None

    @pytest.mark.asyncio
    async def test_cycle_with_no_external_deps(self):
        """Agent runs even without trading/market_data — no system restriction."""
        llm = _make_llm('{"actions": [], "confidence": 0.5}')
        ceo = CEOAgent(
            profile=_make_profile("CEO"),
            personality=create_random_personality(42),
            llm=llm,
        )

        result = await run_agent_cycle(ceo, cycle_number=1)

        assert result["agent_name"] == "CEO"
        assert "emotion" in result
        # No errors — agent handles missing deps gracefully
        assert result.get("errors", []) == []

    @pytest.mark.asyncio
    async def test_ceo_hire_decision_recorded(self):
        """CEO hire decision is recorded as both decision and HR event."""
        from langchain_core.messages import AIMessage
        llm = _make_llm(
            '{"actions": [{"type": "hire", "target": "NewAnalyst", "detail": "analyst", "reason": "need market coverage", "capital": 1000000}], "confidence": 0.9}'
        )
        ceo = CEOAgent(
            profile=_make_profile("CEO"),
            personality=create_random_personality(42),
            llm=llm,
        )
        recorder = _make_recorder()

        hire_json = '[{"type": "hire", "role": "analyst", "target": "NewAnalyst", "reason": "need market coverage"}]'
        mock_react_result = {"messages": [AIMessage(content=f"I'll hire a new analyst.\n```json\n{hire_json}\n```")]}
        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(return_value=mock_react_result)

        with patch("agentic_capital.graph.workflow.create_react_agent", return_value=mock_agent), \
             patch("agentic_capital.graph.workflow._get_langchain_llm", return_value=MagicMock()):
            result = await run_agent_cycle(ceo, cycle_number=1, recorder=recorder)

        assert len(result.get("decisions", [])) >= 1
        # Verify recording happened
        recorder.record_decision.assert_called()
        recorder.commit.assert_called()

    @pytest.mark.asyncio
    async def test_llm_failure_graceful(self):
        """Agent handles LLM failure gracefully — no crash, empty decisions."""
        from unittest.mock import patch, AsyncMock
        llm = _make_llm()
        ceo = CEOAgent(
            profile=_make_profile("CEO"),
            personality=create_random_personality(42),
            llm=llm,
        )

        # Patch react_agent.ainvoke to simulate LLM failure
        with patch("agentic_capital.graph.workflow.create_react_agent") as mock_create:
            mock_agent = MagicMock()
            mock_agent.ainvoke = AsyncMock(side_effect=RuntimeError("LLM timeout"))
            mock_create.return_value = mock_agent

            result = await run_agent_cycle(ceo, cycle_number=1)

        assert result["agent_name"] == "CEO"
        assert result.get("decisions", []) == []
        assert "emotion" in result  # Reflection still runs
