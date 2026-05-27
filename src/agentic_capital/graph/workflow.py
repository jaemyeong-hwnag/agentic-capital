"""Agent workflow — free tool-use (ReAct) loop.

System provides tools. Agent decides everything: what to check, when to trade,
what order, how many times. No fixed pipeline. No forced steps.

The only constraint: capital. The only goal: make money.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

import structlog
from langgraph.prebuilt import create_react_agent

from agentic_capital.adapters.llm.router import build_langchain_chat_model, llm_run_metadata
from agentic_capital.config import settings
from agentic_capital.core.tools.data_query import build_agent_tools, collect_finance_decision_tool_results
from agentic_capital.graph.nodes import record_cycle

if TYPE_CHECKING:
    from agentic_capital.core.agents.base import BaseAgent

logger = structlog.get_logger()

_langchain_llm = None


_QUOTA_ERROR_MARKERS = (
    "resource_exhausted",
    "429",
    "quota",
    "rate limit",
    "retrydelay",
    "please retry",
)


def _parse_retry_delay_seconds(message: str) -> int | None:
    """Parse provider retry hints into seconds."""
    retry_delay_match = re.search(
        r"retryDelay['\"]?\s*[:=]\s*['\"](?P<seconds>\d+(?:\.\d+)?)s",
        message,
        re.IGNORECASE,
    )
    if retry_delay_match:
        return max(1, int(float(retry_delay_match.group("seconds"))))

    human_match = re.search(
        r"retry\s+in\s+"
        r"(?:(?P<hours>\d+(?:\.\d+)?)h)?"
        r"(?:(?P<minutes>\d+(?:\.\d+)?)m)?"
        r"(?:(?P<seconds>\d+(?:\.\d+)?)s)?",
        message,
        re.IGNORECASE,
    )
    if not human_match:
        return None

    hours = float(human_match.group("hours") or 0)
    minutes = float(human_match.group("minutes") or 0)
    seconds = float(human_match.group("seconds") or 0)
    total = int(hours * 3600 + minutes * 60 + seconds)
    return total if total > 0 else None


def _error_retry_seconds(error: str) -> int | None:
    """Return an adaptive retry delay for provider quota/rate-limit errors."""
    normalized = error.lower()
    if not any(marker in normalized for marker in _QUOTA_ERROR_MARKERS):
        return None

    parsed_seconds = _parse_retry_delay_seconds(error)
    if parsed_seconds is None:
        parsed_seconds = 3600

    return min(max(parsed_seconds, 60), 28_800)


def _cycle_error_backoff_seconds(errors: list[str]) -> int:
    """Avoid zero-delay loops after failed cycles."""
    if not errors:
        return 0
    return max(_error_retry_seconds(error) or 300 for error in errors)


def _get_langchain_llm():
    """Lazy-init the configured LangChain-compatible LLM."""
    global _langchain_llm
    if _langchain_llm is None:
        _langchain_llm = build_langchain_chat_model()
    return _langchain_llm


def _build_system_prompt(agent: BaseAgent) -> str:
    """Build compact AI-optimized system prompt.

    ~75% token reduction vs verbose format.
    Uses XML tags (Claude-native), Big5 abbreviations (LLM-universal),
    and LEGEND schema defined once for implicit reuse.

    No workflow prescribed — agent decides everything.
    """
    from agentic_capital.formats.compact import LEGEND, MANDATE, MANDATE_CEO_HR, MANDATE_RISK, psych

    agent_class = type(agent).__name__
    if "CEO" in agent_class:
        role = "CEO"
    elif "Analyst" in agent_class:
        role = "analyst"
    else:
        role = "trader"

    mandate = MANDATE + (MANDATE_CEO_HR if role == "CEO" else "") + MANDATE_RISK

    return (
        f"{LEGEND}\n"
        f"<agent name=\"{agent.name}\" role=\"{role}\">\n"
        f"<phi>{agent.profile.philosophy}</phi>\n"
        f"{psych(agent.personality, agent.emotion)}\n"
        f"</agent>\n"
        f"{mandate}"
    )


def _extract_tool_sequence(messages: list) -> list[dict]:
    """Extract compact tool call chain from LangGraph ReAct messages.

    Format per call: {"t": tool_name, "in": compact_args, "out": result}
    """
    outputs: dict[str, str] = {}
    for msg in messages:
        call_id = getattr(msg, "tool_call_id", None)
        if call_id:
            outputs[call_id] = str(getattr(msg, "content", ""))[:400]

    sequence = []
    for msg in messages:
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            continue
        for tc in tool_calls:
            args = tc.get("args", {})
            args_str = ",".join(f"{k}:{v}" for k, v in args.items() if v not in (None, "", []))
            call_id = tc.get("id", "")
            sequence.append({
                "t": tc.get("name", ""),
                "in": args_str[:200],
                "out": outputs.get(call_id, "")[:300],
            })
    return sequence


def _extract_llm_reasoning(messages: list) -> str:
    """Extract final AI reasoning — last AIMessage with text content (no tool calls)."""
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        if content and isinstance(content, str) and content.strip() and not getattr(msg, "tool_calls", None):
            return content[:2000]
    return ""


def _extract_psychology_context(decisions: list[dict]) -> dict | None:
    """Return the first psychology context decision for cycle-level auditing."""
    psychology_types = {"psychology", "psychology_context", "psychology_evaluation"}
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        decision_type = str(decision.get("type") or decision.get("decision_type") or "")
        if decision_type in psychology_types:
            context = decision.get("psychology_context", decision)
            return context if isinstance(context, dict) else None
    return None


def _should_use_local_finance_flow(agent: BaseAgent) -> bool:
    """Route Trader cycles to the finance sidecar when local finance LLM is active."""
    from agentic_capital.adapters.llm.router import is_local_llm_enabled

    agent_class = type(agent).__name__
    model = settings.local_llm_model.strip().lower()
    return (
        bool(settings.local_finance_pipeline_enabled)
        and is_local_llm_enabled()
        and "trader" in agent_class.lower()
        and model.startswith("finance_")
    )


def _finance_cycle_prompt(agent: BaseAgent, cycle_number: int, symbols: list[str] | None) -> str:
    symbol_text = ",".join(symbols or []) if symbols else ""
    return (
        f"cycle:{cycle_number} finance paper-shadow decision. "
        f"agent:{agent.name}. symbols:{symbol_text or 'unspecified'}. "
        "Use evidence, balance, positions, quote, market session, and risk limit before any trade action."
    )


async def _run_local_finance_agent_cycle(
    agent: BaseAgent,
    cycle_number: int,
    *,
    trading: Any = None,
    market_data: Any = None,
    symbols: list[str] | None = None,
    open_markets: list[str] | None = None,
    recorder: Any = None,
    capital_limit: float | None = None,
) -> dict[str, Any]:
    """Run Trader through the finance-specific sidecar flow instead of ReAct."""
    from datetime import datetime

    from agentic_capital.adapters.llm.local_finance_runtime import run_local_finance_decision_pipeline

    cycle_started_at = datetime.now()
    primary_symbol = (symbols or [settings.local_finance_default_symbol])[0]
    agent_state = {
        "deployment_mode": "paper" if settings.kis_is_paper else "shadow",
        "live_order_enabled": False,
        "account_id": "paper" if settings.kis_is_paper else "shadow",
        "agent_id": str(agent.agent_id),
        "agent_name": agent.name,
        "symbol": primary_symbol,
        "symbols": symbols or [primary_symbol],
        "market": "kr_stock",
        "open_markets": open_markets or [],
        "capital_limit": capital_limit,
        "risk_per_trade_pct": settings.local_finance_risk_per_trade_pct,
    }
    required_safety = {
        "no_profit_guarantee": True,
        "no_live_order_without_permission": True,
        "require_evidence_ids": True,
        "stop_on_missing_context": True,
        "paper_trade_only": True,
    }

    async def _collect_tool_results(payload: dict[str, Any]) -> dict[str, Any]:
        return await collect_finance_decision_tool_results(
            tool_plan_payload=payload.get("tool_plan") if isinstance(payload.get("tool_plan"), dict) else payload,
            trading=trading,
            market_data=market_data,
            symbol=primary_symbol,
            market="kr_stock",
            open_markets=open_markets,
            capital_limit=capital_limit,
            evidence=payload.get("evidence") if isinstance(payload.get("evidence"), list) else [],
            evidence_ids=payload.get("evidence_ids") if isinstance(payload.get("evidence_ids"), list) else [],
        )

    errors: list[str] = []
    result = await run_local_finance_decision_pipeline(
        request_id=f"{agent.agent_id}:{cycle_number}",
        user_question=_finance_cycle_prompt(agent, cycle_number, symbols),
        agent_state=agent_state,
        required_safety=required_safety,
        collect_tool_results=_collect_tool_results,
    )
    if result.get("errors"):
        errors.extend(str(error) for error in result["errors"])

    record = result.get("record") if isinstance(result.get("record"), dict) else {}
    record_type = str(result.get("record_type") or record.get("record_type") or "")
    action = str(result.get("decision", {}).get("action") or record.get("action") or "")
    risk_flags = result.get("risk_flags") if isinstance(result.get("risk_flags"), list) else []
    evidence_ids = result.get("evidence_ids") if isinstance(result.get("evidence_ids"), list) else []
    sidecar_latency_ms = result.get("sidecar_latency_ms")
    sidecar_calls = result.get("sidecar_calls", []) if isinstance(result.get("sidecar_calls"), list) else []
    first_failing_stage = result.get("first_failing_stage")

    all_decisions: list[dict[str, Any]] = []
    if record_type == "finance_paper_shadow_decision" and action.upper() != "NO_CONTEXT":
        all_decisions.append({
            "type": "finance_paper_shadow_decision",
            "action": action,
            "symbol": record.get("symbol") or primary_symbol,
            "reason": result.get("decision", {}).get("reason", ""),
            "confidence": result.get("decision", {}).get("confidence", 0.0),
            "evidence_ids": evidence_ids,
            "risk_flags": risk_flags,
        })

    await record_cycle(
        agent=agent,
        cycle_number=cycle_number,
        decisions=[],
        messages=[],
        recorder=recorder,
    )

    cycle_completed_at = datetime.now()
    next_cycle_seconds = max(int(settings.simulation_min_cycle_seconds), 1)
    tool_results = result.get("tool_results") if isinstance(result.get("tool_results"), dict) else {}
    tool_seq = [
        {"t": name, "in": "", "out": json.dumps(value, ensure_ascii=False, default=str)[:300]}
        for name, value in tool_results.items()
        if not name.startswith("_")
    ]
    reasoning = json.dumps(
        {
            "record_type": record_type,
            "action": action,
            "failure_type": record.get("failure_type"),
            "risk_flags": risk_flags,
            "evidence_ids": evidence_ids,
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    emotion_snap = {
        "V": round(agent.emotion.valence, 2),
        "AR": round(agent.emotion.arousal, 2),
        "D": round(agent.emotion.dominance, 2),
        "ST": round(agent.emotion.stress, 2),
        "CF": round(agent.emotion.confidence, 2),
    }
    economics_snapshot = {
        **llm_run_metadata(),
        "finance_record_type": record_type,
        "sidecar_latency_ms": sidecar_latency_ms,
        "evidence_ids": evidence_ids,
        "risk_flags": risk_flags,
        "sidecar_calls": sidecar_calls,
        "first_failing_stage": first_failing_stage,
    }
    if recorder:
        try:
            if record_type == "finance_paper_shadow_decision":
                await recorder.record_finance_paper_shadow_decision(
                    agent_id=agent.agent_id,
                    record=record,
                    cycle_number=cycle_number,
                    sidecar_latency_ms=sidecar_latency_ms,
                    evidence_ids=evidence_ids,
                    risk_flags=risk_flags,
                    sidecar_calls=sidecar_calls,
                    first_failing_stage=first_failing_stage,
                )
            else:
                await recorder.record_raw_model_failure(
                    agent_id=agent.agent_id,
                    failure=record,
                    cycle_number=cycle_number,
                    sidecar_latency_ms=sidecar_latency_ms,
                    evidence_ids=evidence_ids,
                    risk_flags=risk_flags,
                    sidecar_calls=sidecar_calls,
                    first_failing_stage=first_failing_stage,
                )
            await recorder.record_agent_cycle(
                agent_id=agent.agent_id,
                agent_name=agent.name,
                cycle_number=cycle_number,
                tool_sequence=tool_seq,
                llm_reasoning=reasoning,
                emotion_snapshot=emotion_snap,
                economics_snapshot=economics_snapshot,
                started_at=cycle_started_at,
                completed_at=cycle_completed_at,
                decisions_count=len(all_decisions),
                errors_count=len(errors),
                next_cycle_seconds=next_cycle_seconds,
            )
            await recorder.commit()
        except Exception:
            logger.warning("local_finance_cycle_record_failed", agent=agent.name)

    logger.info(
        "local_finance_agent_cycle_complete",
        agent=agent.name,
        cycle=cycle_number,
        record_type=record_type,
        action=action,
        decisions=len(all_decisions),
        errors=len(errors),
        sidecar_latency_ms=sidecar_latency_ms,
    )
    return {
        "agent_id": str(agent.agent_id),
        "agent_name": agent.name,
        "cycle_number": cycle_number,
        "decisions": all_decisions,
        "messages_to_send": [],
        "errors": errors,
        "next_cycle_seconds": next_cycle_seconds,
        "finance_record": record,
        "finance_record_type": record_type,
        "finance_no_context": record_type == "raw_model_failure" or action.upper() == "NO_CONTEXT",
        "sidecar_latency_ms": sidecar_latency_ms,
        "sidecar_calls": sidecar_calls,
        "first_failing_stage": first_failing_stage,
        "evidence_ids": evidence_ids,
        "risk_flags": risk_flags,
        "emotion": {
            "valence": agent.emotion.valence,
            "arousal": agent.emotion.arousal,
            "dominance": agent.emotion.dominance,
            "stress": agent.emotion.stress,
            "confidence": agent.emotion.confidence,
        },
    }


async def run_agent_cycle(
    agent: BaseAgent,
    cycle_number: int,
    *,
    trading: Any = None,
    market_data: Any = None,
    symbols: list[str] | None = None,
    open_markets: list[str] | None = None,
    recorder: Any = None,
    capital_limit: float | None = None,
) -> dict:
    """Run one autonomous cycle for an agent using ReAct tool-use loop.

    The agent receives all tools and decides freely what to do.
    No workflow, no forced steps.

    Returns:
        dict with 'decisions', 'messages', 'errors' for the engine to process.
    """
    from datetime import datetime

    from langchain_core.messages import HumanMessage

    from agentic_capital.core.tools.data_query import _build_dynamic_tool

    if _should_use_local_finance_flow(agent):
        return await _run_local_finance_agent_cycle(
            agent,
            cycle_number,
            trading=trading,
            market_data=market_data,
            symbols=symbols,
            open_markets=open_markets,
            recorder=recorder,
            capital_limit=capital_limit,
        )

    # Load AI-created tools from DB and build StructuredTool instances
    preloaded: list = []
    if recorder:
        try:
            specs = await recorder.load_tools()
            for spec in specs:
                t = _build_dynamic_tool(spec, trading, market_data, recorder)
                if t is not None:
                    preloaded.append(t)
            if preloaded:
                logger.info("dynamic_tools_loaded", agent=agent.name, count=len(preloaded))
        except Exception:
            logger.warning("dynamic_tools_load_failed", agent=agent.name)

    tools, decisions_sink, messages_sink, wakeup_sink = build_agent_tools(
        trading=trading,
        market_data=market_data,
        recorder=recorder,
        agent_id=str(agent.agent_id),
        agent_name=agent.name,
        agent_memory=getattr(agent, "_memory", None),
        preloaded_tools=preloaded,
        capital_limit=capital_limit,
    )

    system_prompt = _build_system_prompt(agent)
    llm = _get_langchain_llm()

    react_agent = create_react_agent(llm, tools, prompt=system_prompt)

    cycle_trigger = f"cycle:{cycle_number}"

    logger.info("agent_cycle_start", agent=agent.name, cycle=cycle_number)

    errors: list[str] = []
    result_messages = []
    cycle_started_at = datetime.now()

    try:
        result = await react_agent.ainvoke(
            {"messages": [HumanMessage(content=cycle_trigger)]},
            config={"recursion_limit": 200},  # type: ignore[arg-type]
        )
        result_messages = result.get("messages", [])
    except Exception as e:
        errors.append(str(e))
        logger.exception("agent_react_cycle_failed", agent=agent.name, cycle=cycle_number)

    cycle_completed_at = datetime.now()

    # Extract any decisions from LLM output (hire/fire/org actions from text)
    org_decisions = _extract_org_decisions(result_messages)

    all_decisions = decisions_sink + org_decisions
    psychology_context = _extract_psychology_context(all_decisions)

    # Record decisions/emotions/messages to DB
    await record_cycle(
        agent=agent,
        cycle_number=cycle_number,
        decisions=all_decisions,
        messages=messages_sink,
        recorder=recorder,
    )

    # Agent-requested wakeup delay takes priority. On failures, never loop at
    # zero delay: provider quota errors can otherwise burn the entire day.
    error_backoff_seconds = _cycle_error_backoff_seconds(errors)
    next_cycle_seconds = wakeup_sink[-1] if wakeup_sink else error_backoff_seconds

    # Record full LLM activity trace: tool sequence + reasoning
    if recorder:
        try:
            tool_seq = _extract_tool_sequence(result_messages)
            reasoning = _extract_llm_reasoning(result_messages)
            emotion_snap = {
                "V": round(agent.emotion.valence, 2),
                "AR": round(agent.emotion.arousal, 2),
                "D": round(agent.emotion.dominance, 2),
                "ST": round(agent.emotion.stress, 2),
                "CF": round(agent.emotion.confidence, 2),
            }
            await recorder.record_agent_cycle(
                agent_id=agent.agent_id,
                agent_name=agent.name,
                cycle_number=cycle_number,
                tool_sequence=tool_seq,
                llm_reasoning=reasoning,
                emotion_snapshot=emotion_snap,
                economics_snapshot=llm_run_metadata(),
                started_at=cycle_started_at,
                completed_at=cycle_completed_at,
                decisions_count=len(all_decisions),
                errors_count=len(errors),
                next_cycle_seconds=next_cycle_seconds,
                psychology_context=psychology_context,
            )
            await recorder.commit()
        except Exception:
            logger.warning("agent_cycle_record_failed", agent=agent.name)

    logger.info(
        "agent_cycle_complete",
        agent=agent.name,
        cycle=cycle_number,
        decisions=len(all_decisions),
        tool_calls=len(decisions_sink),
        errors=len(errors),
        error_backoff_seconds=error_backoff_seconds,
        next_cycle_seconds=next_cycle_seconds,
    )

    return {
        "agent_id": str(agent.agent_id),
        "agent_name": agent.name,
        "cycle_number": cycle_number,
        "decisions": all_decisions,
        "messages_to_send": messages_sink,
        "errors": errors,
        "next_cycle_seconds": next_cycle_seconds,
        "emotion": {
            "valence": agent.emotion.valence,
            "arousal": agent.emotion.arousal,
            "dominance": agent.emotion.dominance,
            "stress": agent.emotion.stress,
            "confidence": agent.emotion.confidence,
        },
    }


def _extract_org_decisions(messages: list) -> list[dict]:
    """Extract hire/fire/create_role decisions from agent messages.

    CEOs may output org decisions in their final text response.
    We parse these from the last AIMessage content.
    """
    import json
    import re

    for msg in reversed(messages):
        # Check for AIMessage with text content
        content = getattr(msg, "content", None)
        if not content or not isinstance(content, str):
            continue

        # Try JSON block
        json_match = re.search(r"```json\s*(\[.*?\]|\{.*?\})\s*```", content, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                if isinstance(parsed, list):
                    return [d for d in parsed if isinstance(d, dict) and "type" in d]
                if isinstance(parsed, dict) and "type" in parsed:
                    return [parsed]
            except (json.JSONDecodeError, ValueError):
                pass

        # Try bare JSON array/object
        for pattern in [r"(\[[\s\S]*?\])", r"(\{[\s\S]*?\})"]:
            match = re.search(pattern, content)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                    if isinstance(parsed, list):
                        org_types = {"hire", "fire", "create_role", "abolish_role"}
                        org_decisions = [d for d in parsed if isinstance(d, dict) and d.get("type") in org_types]
                        if org_decisions:
                            return org_decisions
                except (json.JSONDecodeError, ValueError):
                    pass

    return []
