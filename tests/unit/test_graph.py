"""Unit tests for agent cycle workflow and recording."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from agentic_capital.core.agents.analyst import AnalystAgent
from agentic_capital.core.agents.base import AgentProfile
from agentic_capital.core.agents.ceo import CEOAgent
from agentic_capital.core.agents.factory import create_random_personality
from agentic_capital.core.agents.trader import TraderAgent
from agentic_capital.graph.nodes import record_cycle
from agentic_capital.graph.state import AgentCycleResult, AgentWorkflowState
from agentic_capital.graph.workflow import (
    _agent_response_quality_issues,
    _build_system_prompt,
    _error_retry_seconds,
    _exception_summary,
    _extract_psychology_context,
    _extract_tool_sequence,
    _filter_tools_for_agent,
    _psychology_cycle_input,
    run_agent_cycle,
)
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


def _tool(name: str):
    tool = MagicMock()
    tool.name = name
    return tool


def _make_recorder():
    recorder = MagicMock()
    recorder.record_emotion = AsyncMock()
    recorder.record_decision = AsyncMock()
    recorder.record_psychology_context = AsyncMock()
    recorder.record_hr_event = AsyncMock()
    recorder.record_agent_message = AsyncMock()
    recorder.record_position_snapshot = AsyncMock()
    recorder.commit = AsyncMock()
    return recorder


def _psychology_result(phase: str = "post_agent_cycle") -> dict:
    return {
        "phase": phase,
        "ok": True,
        "model": "psychology_model_suite",
        "status_code": 200,
        "latency_ms": 11,
        "repair_applied": None,
        "context": {
            "signals": [],
            "agent_state_patch": {"attention": "risk_review"},
            "evidence_ids": ["memory-1"],
            "confidence": 0.72,
            "uncertainty": ["requires finance tools before any trade"],
            "risk_tags": ["overconfidence_risk"],
            "allowed_downstream_use": "context_only",
        },
        "soft_context": {
            "risk_tags": ["overconfidence_risk"],
            "evidence_ids": ["memory-1"],
            "confidence": 0.72,
            "uncertainty": ["requires finance tools before any trade"],
            "agent_state_patch": {"attention": "risk_review"},
            "use_as": "soft_risk_context_not_alpha",
            "forbidden_use": [
                "trade_action",
                "order_quantity",
                "order_permission",
                "capital_allocation",
                "risk_limit_override",
            ],
        },
    }


def test_extract_tool_sequence_preserves_duplicate_local_call_ids_in_order() -> None:
    messages = [
        AIMessage(content="", tool_calls=[{"name": "get_balance", "args": {}, "id": "local_call_0"}]),
        ToolMessage(content="tot:5000000,avl:5000000,ccy:KRW", tool_call_id="local_call_0", name="get_balance"),
        AIMessage(content="", tool_calls=[{"name": "get_ohlcv", "args": {"symbol": "005930"}, "id": "local_call_0"}]),
        ToolMessage(content="@ohlcv:005930[20](dt,o,h,l,c,v)", tool_call_id="local_call_0", name="get_ohlcv"),
    ]

    assert _extract_tool_sequence(messages) == [
        {"t": "get_balance", "in": "", "out": "tot:5000000,avl:5000000,ccy:KRW"},
        {"t": "get_ohlcv", "in": "symbol:005930", "out": "@ohlcv:005930[20](dt,o,h,l,c,v)"},
    ]


def test_psychology_cycle_input_compacts_trace_decisions_and_tool_outputs() -> None:
    ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=_make_llm())
    payload = _psychology_cycle_input(
        agent=ceo,
        cycle_number=3,
        phase="post_agent_cycle",
        text="x" * 3000,
        decisions=[{"type": "finance_paper_shadow_decision", "action": "CALL_TOOL", "record": {"raw": "y" * 3000}}],
        tool_sequence=[{"t": "get_ohlcv", "in": "symbol:005930", "out": "@ohlcv " + ("z" * 2000)}],
    )

    assert len(payload) < 1400
    assert "finance_paper_shadow_decision" in payload
    assert "y" * 100 not in payload
    assert "z" * 200 not in payload


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
    async def test_records_psychology_context_without_decision_route(self):
        ceo = CEOAgent(profile=_make_profile(), personality=create_random_personality(42), llm=_make_llm())
        recorder = _make_recorder()
        decisions = [{
            "type": "psychology_context",
            "source": "psychology_behavior_bias_model",
            "psychology_context": {
                "agent_state_patch": {"attention": "risk_review"},
                "evidence_ids": ["memory-1"],
                "confidence": 0.72,
                "uncertainty": ["requires finance tools before trade"],
                "risk_tags": ["overconfidence_risk"],
                "allowed_downstream_use": "context_only",
            },
        }]
        await record_cycle(ceo, 1, decisions=decisions, messages=[], recorder=recorder)

        recorder.record_psychology_context.assert_called_once()
        recorder.record_decision.assert_not_called()

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


class TestPsychologyContextExtraction:
    def test_extracts_first_psychology_context_for_cycle_record(self):
        context = {
            "evidence_ids": ["memory-1"],
            "confidence": 0.72,
            "uncertainty": ["requires finance tools"],
            "allowed_downstream_use": "context_only",
        }
        result = _extract_psychology_context([
            {"type": "strategy", "detail": "observe"},
            {"type": "psychology_context", "psychology_context": context},
        ])

        assert result == context

    def test_ignores_non_psychology_decisions(self):
        assert _extract_psychology_context([{"type": "trade", "action": "HOLD"}]) is None


class TestAgentToolFiltering:
    def test_ceo_does_not_receive_trade_execution_tools(self):
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=_make_llm())
        tools = [
            _tool("get_balance"),
            _tool("get_fills"),
            _tool("submit_order"),
            _tool("cancel_order"),
            _tool("evaluate_reallocation"),
            _tool("send_message"),
        ]

        names = {tool.name for tool in _filter_tools_for_agent(ceo, tools)}

        assert "get_balance" in names
        assert "send_message" in names
        assert "submit_order" not in names
        assert "cancel_order" not in names
        assert "evaluate_reallocation" not in names
        assert "get_fills" not in names

    def test_non_trader_prompt_avoids_direct_order_tool_mandate(self):
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=_make_llm())
        prompt = _build_system_prompt(ceo)

        assert "trade US stocks/ETFs during pre-market and regular hours via submit_order" not in prompt
        assert "send instructions to Trader" in prompt
        assert "Respond in compact Korean or English only" in prompt
        assert "KRX:POST" in prompt
        assert "OBS|..." in prompt

    def test_non_trader_response_quality_flags_roleplay_drift(self):
        issues = _agent_response_quality_issues(
            "ceo",
            "¿Qué tal si actualizamos quote symbol KRX:POST? If you need further assistance, please let me know.",
        )

        assert "language_drift_non_ko_en" in issues
        assert "generic_assistant_response" in issues
        assert "market_status_token_confusion" in issues
        assert _agent_response_quality_issues("trader", "¿Qué tal si actualizamos quote symbol KRX:POST?") == []

    def test_trader_keeps_trade_tools_for_legacy_react_runs(self):
        trader = TraderAgent(
            profile=_make_profile("Trader"),
            personality=create_random_personality(42),
            llm=_make_llm(),
            trading=_make_trading(),
        )
        tools = [_tool("submit_order"), _tool("cancel_order"), _tool("get_fills")]

        assert {tool.name for tool in _filter_tools_for_agent(trader, tools)} == {
            "submit_order",
            "cancel_order",
            "get_fills",
        }


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
             patch("agentic_capital.graph.workflow._get_langchain_llm", return_value=MagicMock()), \
             patch("agentic_capital.graph.workflow._run_psychology_observation", new_callable=AsyncMock):
            result = await run_agent_cycle(ceo, cycle_number=1)

        assert result["agent_name"] == "CEO"
        assert result["cycle_number"] == 1
        assert "decisions" in result
        assert "emotion" in result
        assert "next_cycle_seconds" in result

    @pytest.mark.asyncio
    async def test_full_cycle_analyst(self):
        analyst = AnalystAgent(profile=_make_profile("Analyst"), personality=create_random_personality(42), llm=_make_llm())
        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(return_value=self._mock_react_result())

        with patch("agentic_capital.graph.workflow.create_react_agent", return_value=mock_agent), \
             patch("agentic_capital.graph.workflow._get_langchain_llm", return_value=MagicMock()), \
             patch("agentic_capital.graph.workflow._run_psychology_observation", new_callable=AsyncMock):
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

        with patch("agentic_capital.graph.workflow.settings.local_finance_pipeline_enabled", False), \
             patch("agentic_capital.graph.workflow.create_react_agent", return_value=mock_agent), \
             patch("agentic_capital.graph.workflow._get_langchain_llm", return_value=MagicMock()), \
             patch("agentic_capital.graph.workflow._run_psychology_observation", new_callable=AsyncMock):
            result = await run_agent_cycle(
                trader, cycle_number=1,
                trading=trading,
                symbols=["005930"],
            )

        assert result["agent_name"] == "Trader"

    @pytest.mark.asyncio
    async def test_local_finance_trader_uses_sidecar_pipeline(self):
        trading = _make_trading()
        market_data = _make_market_data()
        trader = TraderAgent(
            profile=_make_profile("Trader"),
            personality=create_random_personality(42),
            llm=_make_llm(),
            trading=trading,
        )
        recorder = _make_recorder()
        recorder.record_finance_paper_shadow_decision = AsyncMock()
        recorder.record_raw_model_failure = AsyncMock()
        recorder.record_agent_cycle = AsyncMock()

        pipeline_result = {
            "record_type": "raw_model_failure",
            "record": {
                "record_type": "raw_model_failure",
                "failure_type": "call_tool_missing_required_tools",
                "action": "NO_CONTEXT",
                "evidence_ids": [],
            },
            "decision": {"action": "NO_CONTEXT", "reason": "근거 부족"},
            "tool_results": {"get_balance": {"available": 1000000}},
            "evidence_ids": [],
            "risk_flags": ["missing_context"],
            "sidecar_latency_ms": 12,
            "sidecar_calls": [{"stage": "finance_tool_planner_model", "ok": False, "status_code": 503}],
            "first_failing_stage": "finance_tool_planner_model",
        }

        with patch("agentic_capital.graph.workflow.settings.local_finance_pipeline_enabled", True), \
             patch("agentic_capital.graph.workflow.settings.local_llm_model", "finance_decision_model"), \
             patch("agentic_capital.adapters.llm.router.settings.llm_provider", "gemini"), \
             patch("agentic_capital.graph.workflow.create_react_agent") as mock_react, \
             patch(
                 "agentic_capital.graph.workflow._run_psychology_observation",
                 AsyncMock(side_effect=[
                     _psychology_result("pre_agent_cycle"),
                     _psychology_result("post_agent_cycle"),
                 ]),
             ) as mock_psychology, \
             patch(
                 "agentic_capital.adapters.llm.local_finance_runtime.run_local_finance_decision_pipeline",
                 AsyncMock(return_value=pipeline_result),
             ) as mock_pipeline:
            result = await run_agent_cycle(
                trader,
                cycle_number=1,
                trading=trading,
                market_data=market_data,
                symbols=["005930"],
                open_markets=["KRX"],
                recorder=recorder,
                capital_limit=1_000_000,
            )

        mock_react.assert_not_called()
        mock_pipeline.assert_awaited_once()
        assert mock_pipeline.await_args.kwargs["psychology_context"]["allowed_downstream_use"] == "context_only"
        assert mock_psychology.await_count == 2
        recorder.record_raw_model_failure.assert_awaited_once()
        assert recorder.record_raw_model_failure.await_args.kwargs["first_failing_stage"] == "finance_tool_planner_model"
        economics = recorder.record_agent_cycle.await_args.kwargs["economics_snapshot"]
        assert economics["psychology_context"]["use_as"] == "soft_risk_context_not_alpha"
        assert [item["phase"] for item in economics["psychology_observations"]] == [
            "pre_agent_cycle",
            "post_agent_cycle",
        ]
        assert result["finance_no_context"] is True
        assert result["first_failing_stage"] == "finance_tool_planner_model"
        assert result["decisions"] == []

    @pytest.mark.asyncio
    async def test_agent_cycle_records_pre_post_psychology_context(self):
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=_make_llm())
        recorder = _make_recorder()
        recorder.record_agent_cycle = AsyncMock()
        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(return_value=self._mock_react_result())

        with patch("agentic_capital.graph.workflow.create_react_agent", return_value=mock_agent), \
             patch("agentic_capital.graph.workflow._get_langchain_llm", return_value=MagicMock()), \
             patch(
                 "agentic_capital.graph.workflow._run_psychology_observation",
                 AsyncMock(side_effect=[
                     _psychology_result("pre_agent_cycle"),
                     _psychology_result("post_agent_cycle"),
                 ]),
             ) as mock_psychology:
            result = await run_agent_cycle(ceo, cycle_number=7, recorder=recorder)

        assert result["agent_name"] == "CEO"
        assert mock_psychology.await_count == 2
        phases = [call.kwargs["phase"] for call in mock_psychology.await_args_list]
        assert phases == ["pre_agent_cycle", "post_agent_cycle"]
        economics = recorder.record_agent_cycle.await_args.kwargs["economics_snapshot"]
        assert economics["psychology_context"]["use_as"] == "soft_risk_context_not_alpha"
        assert economics["psychology_context"]["forbidden_use"] == [
            "trade_action",
            "order_quantity",
            "order_permission",
            "capital_allocation",
            "risk_limit_override",
        ]
        assert economics["agent_request"]["agent_role"] == "ceo"
        assert economics["agent_request"]["cycle_trigger"] == "cycle:7"
        assert economics["agent_response"]["tool_calls_count"] == len(
            recorder.record_agent_cycle.await_args.kwargs["tool_sequence"]
        )
        assert economics["agent_response"]["next_action"] == "continue_cycle"
        assert economics["agent_response"]["quality_issues"] == []
        assert [item["phase"] for item in economics["psychology_observations"]] == [
            "pre_agent_cycle",
            "post_agent_cycle",
        ]

    @pytest.mark.asyncio
    async def test_handles_react_failure_gracefully(self):
        """If ReAct agent throws, cycle still returns with errors."""
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=_make_llm())
        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(side_effect=RuntimeError("LLM provider crashed"))

        with patch("agentic_capital.graph.workflow.create_react_agent", return_value=mock_agent), \
             patch("agentic_capital.graph.workflow._get_langchain_llm", return_value=MagicMock()), \
             patch("agentic_capital.graph.workflow._run_psychology_observation", new_callable=AsyncMock):
            result = await run_agent_cycle(ceo, cycle_number=1)

        assert result["agent_name"] == "CEO"
        assert len(result["errors"]) > 0
        assert result["next_cycle_seconds"] == 300

    def test_exception_summary_uses_type_when_message_empty(self):
        assert _exception_summary(TimeoutError()) == "TimeoutError"
        assert _exception_summary(RuntimeError("provider crashed")) == "provider crashed"

    @pytest.mark.asyncio
    async def test_quota_failure_uses_provider_retry_delay(self):
        """Provider quota hints should slow the loop instead of retrying immediately."""
        ceo = CEOAgent(profile=_make_profile("CEO"), personality=create_random_personality(42), llm=_make_llm())
        mock_agent = MagicMock()
        message = (
            "Error calling model 'gemini-2.5-flash' (RESOURCE_EXHAUSTED): "
            "429 RESOURCE_EXHAUSTED. Quota exceeded. retryDelay': '26105s'"
        )
        mock_agent.ainvoke = AsyncMock(side_effect=RuntimeError(message))

        with patch("agentic_capital.graph.workflow.create_react_agent", return_value=mock_agent), \
             patch("agentic_capital.graph.workflow._get_langchain_llm", return_value=MagicMock()), \
             patch("agentic_capital.graph.workflow._run_psychology_observation", new_callable=AsyncMock):
            result = await run_agent_cycle(ceo, cycle_number=1)

        assert result["agent_name"] == "CEO"
        assert len(result["errors"]) == 1
        assert result["next_cycle_seconds"] == 26105

    def test_parses_human_quota_retry_delay(self):
        """Gemini human-readable retry hints should be parsed for long backoff."""
        error = "Quota exceeded. Please retry in 7h15m5.72624757s."
        assert _error_retry_seconds(error) == 26105

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
             patch("agentic_capital.graph.workflow._get_langchain_llm", return_value=MagicMock()), \
             patch("agentic_capital.graph.workflow._run_psychology_observation", new_callable=AsyncMock):
            result = await run_agent_cycle(ceo, cycle_number=1)

        org_decisions = [d for d in result["decisions"] if d.get("type") == "hire"]
        assert len(org_decisions) == 1
        assert org_decisions[0]["role"] == "analyst"
