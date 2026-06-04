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
from agentic_capital.core.tools.data_query import (
    _market_signal_from_ohlcv,
    _serialise_ohlcv,
    build_agent_tools,
    collect_finance_decision_tool_results,
)
from agentic_capital.graph.nodes import record_cycle
from agentic_capital.ports.trading import infer_option_type

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

_NON_TRADER_BLOCKED_TOOL_NAMES = frozenset({
    "cancel_order",
    "evaluate_reallocation",
    "get_fills",
    "set_position_policy",
    "submit_order",
})

_GENERIC_ASSISTANT_PHRASES = (
    "if you need further assistance",
    "please let me know",
    "feel free to let me know",
    "how can i help",
    "it seems there was an attempt to invoke",
    "there was an attempt to invoke",
    "추가 도움이 필요",
    "도움이 필요하시면",
)

_MARKET_STATUS_ANSWER_PHRASES = (
    "the current market status is",
    "market status update indicating",
    "you've provided a market status update",
    "you have provided a market status update",
    "invalid placeholder symbol",
    "가상_symbol",
    "가상 symbol",
    "거래되지 않는 symbol",
    "현재 세션으로는",
)

_PORTFOLIO_STATE_CLAIM_PHRASES = (
    "current positions:",
    "avg prices:",
    "average prices:",
    "unrealized p&l",
    "unrealized p&ls",
    "unrealized pnl",
    "보유 포지션:",
    "평균 단가:",
    "미실현 손익",
)

_NON_KO_EN_MARKERS = (
    "¿",
    "¡",
    "qué",
    "tal si",
    "actualizamos",
    "con esta",
    "podemos",
    "工具",
    "调用",
    "错误",
    "参数",
    "正确",
    "如果",
    "需要",
    "在这种情况下",
)

_MARKET_STATUS_TOKENS = (
    "krx:pre",
    "krx:post",
    "krx:regular",
    "krx:closed",
    "nasdaq:pre",
    "nasdaq:post",
    "nasdaq:regular",
    "nasdaq:closed",
    "nyse:pre",
    "nyse:post",
    "nyse:regular",
    "nyse:closed",
)

_RECOVERABLE_FINANCE_RAW_FAILURES = frozenset({
    "call_tool_loop_with_sufficient_tool_evidence",
    "trade_missing_notional",
})


def _compact_text(value: Any, *, limit: int = 500) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else f"{compact[:limit].rstrip()}..."


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


def _exception_summary(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return type(exc).__name__


def _agent_runtime_failure_stage(error: str) -> str:
    """Classify local agent runtime failures for recorder/guard diagnostics."""
    normalized = error.lower()
    if "timeout" in normalized or "readtimeout" in normalized or error == "TimeoutError":
        return "local_agent_runtime_timeout"
    if "connect" in normalized or "connection" in normalized:
        return "local_agent_runtime_connection"
    return "local_agent_runtime"


def _agent_runtime_fallback_reasoning(
    *,
    agent: BaseAgent,
    cycle_number: int,
    symbols: list[str] | None,
    open_markets: list[str] | None,
    error: str,
) -> str:
    """Return a deterministic non-trading operating note when local agent LLM fails."""
    role = _agent_tool_role(agent)
    markets_text = ",".join(open_markets or []) if open_markets else "none"
    symbols_text = ",".join(symbols or []) if symbols else "unspecified"
    stage = _agent_runtime_failure_stage(error)
    if role == "ceo":
        task = "Trader-Gamma: continue finance sidecar paper-shadow review only; Analyst-Beta: refresh evidence when runtime recovers"
    else:
        task = "Trader-Gamma: use finance sidecar tools before any trade; report missing evidence and risk flags"
    return (
        f"OBS|cycle={cycle_number}; role={role}; local_agent_runtime_status=failed; "
        f"first_failing_stage={stage}; watchlist={symbols_text}; market_status={markets_text}. "
        f"TRADER_TASK|{task}. "
        "NEXT|record failure, keep paper-only mode, retry local agent runtime after guarded backoff."
    )


def _agent_response_repair_reasoning(
    *,
    agent: BaseAgent,
    cycle_number: int,
    symbols: list[str] | None,
    open_markets: list[str] | None,
    quality_issues: list[str],
    tool_sequence: list[dict],
) -> str:
    """Repair non-Trader assistant drift into an operating note."""
    role = _agent_tool_role(agent)
    markets_text = ",".join(open_markets or []) if open_markets else "none"
    symbols_text = ",".join(symbols or []) if symbols else "unspecified"
    tool_hint = ",".join(str(item.get("t")) for item in tool_sequence[:4] if item.get("t")) or "none"
    if role == "ceo":
        task = "Trader-Gamma: run finance sidecar paper-shadow review on watchlist; Analyst-Beta: attach evidence gaps only"
    else:
        task = "Trader-Gamma: review finance sidecar evidence, balance, quote, positions, session, and risk limit before any order"
    return (
        f"OBS|cycle={cycle_number}; role={role}; response_repaired=true; "
        f"quality_issues={','.join(quality_issues)}; watchlist={symbols_text}; "
        f"market_status={markets_text}; tools_seen={tool_hint}. "
        f"TRADER_TASK|{task}. "
        "NEXT|continue local-only paper loop; do not ask user; do not execute orders outside Trader finance flow."
    )


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
        role = str(getattr(agent, "role", "") or "analyst")
    else:
        role = "trader"

    mandate = MANDATE
    if role != "trader":
        mandate = mandate.replace(
            "|USE_ALL_MARKETS — trade US stocks/ETFs during pre-market and regular hours via submit_order(market=us_stock)",
            "|USE_ALL_MARKETS — analyze opportunities and send instructions to Trader; do not call order tools",
        )
        mandate += (
            "\n<role_boundary>"
            "Only Trader may enter the finance sidecar trading flow. "
            "CEO/analyst agents must not submit, cancel, or directly execute orders; "
            "send instructions or analysis to Trader instead. "
            "Use only listed tool names exactly; if a needed tool is unavailable, send a message or request_wakeup. "
            "Respond in compact Korean or English only; never use Spanish, Hindi, or other languages. "
            "Do not produce generic assistant help text. Produce an investment-company operating note. "
            "Treat KRX/NASDAQ/NYSE market-session tokens such as KRX:POST or NASDAQ:CLOSED as market status, not symbols. "
            "If you call tools, call them through the runtime only; do not paste raw JSON tool calls into the final answer. "
            "TRADER_TASK must be a prose instruction, never a JSON object or tool schema. "
            "Use this compact shape when possible: OBS|... TRADER_TASK|... NEXT|..."
            "</role_boundary>"
        )
    mandate += (MANDATE_CEO_HR if role == "CEO" else "") + MANDATE_RISK

    return (
        f"{LEGEND}\n"
        f"<agent name=\"{agent.name}\" role=\"{role}\">\n"
        f"<phi>{agent.profile.philosophy}</phi>\n"
        f"{psych(agent.personality, agent.emotion)}\n"
        f"</agent>\n"
        f"{mandate}"
    )


def _agent_tool_role(agent: BaseAgent) -> str:
    agent_class = type(agent).__name__.lower()
    if "trader" in agent_class:
        return "trader"
    if "ceo" in agent_class:
        return "ceo"
    return "analyst"


def _filter_tools_for_agent(agent: BaseAgent, tools: list[Any]) -> list[Any]:
    """Keep CEO/Analyst out of order/fill execution tools.

    Trader uses the finance sidecar when local finance is enabled, so ReAct
    order tools should only exist for legacy/non-finance Trader runs.
    """
    if _agent_tool_role(agent) == "trader":
        return tools

    filtered = [
        tool for tool in tools
        if str(getattr(tool, "name", "")) not in _NON_TRADER_BLOCKED_TOOL_NAMES
    ]
    removed = len(tools) - len(filtered)
    if removed:
        logger.info(
            "agent_trade_tools_filtered",
            agent=agent.name,
            role=_agent_tool_role(agent),
            removed=removed,
        )
    return filtered


def _extract_tool_sequence(messages: list) -> list[dict]:
    """Extract compact tool call chain from LangGraph ReAct messages.

    Format per call: {"t": tool_name, "in": compact_args, "out": result}
    """
    sequence: list[dict] = []
    pending: list[dict] = []
    for msg in messages:
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                args = tc.get("args", {})
                args_str = ",".join(f"{k}:{v}" for k, v in args.items() if v not in (None, "", []))
                item = {
                    "t": tc.get("name", ""),
                    "in": args_str[:200],
                    "out": "",
                    "_id": tc.get("id", ""),
                }
                pending.append(item)
                sequence.append(item)

        call_id = getattr(msg, "tool_call_id", None)
        if call_id:
            content = str(getattr(msg, "content", ""))[:300]
            tool_name = str(getattr(msg, "name", "") or "")
            match = next(
                (
                    item for item in pending
                    if not item.get("out")
                    and (item.get("_id") == call_id or (tool_name and item.get("t") == tool_name))
                ),
                None,
            )
            if match is None:
                match = {"t": tool_name or str(call_id), "in": "", "out": "", "_id": call_id}
                sequence.append(match)
            match["out"] = content
            if match in pending:
                pending.remove(match)

    for item in sequence:
        item.pop("_id", None)
    return sequence


def _extract_llm_reasoning(messages: list) -> str:
    """Extract final AI reasoning — last AIMessage with text content (no tool calls)."""
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        if content and isinstance(content, str) and content.strip() and not getattr(msg, "tool_calls", None):
            return content[:2000]
    return ""


def _agent_response_quality_issues(role: str, reasoning: str) -> list[str]:
    """Flag non-Trader roleplay drift for recorder/ops visibility."""
    if role == "trader" or not reasoning.strip():
        return []

    normalized = " ".join(reasoning.split()).lower()
    issues: list[str] = []
    raw_tool_call_final = (
        normalized.startswith('{"tool_calls"')
        or '"tool_calls"' in normalized
        or normalized.startswith("_tool_calls=")
        or "_tool_calls=[" in normalized
        or bool(re.search(r'[{[]\s*"name"\s*:\s*"get_[a-z_]+"', normalized))
    )
    if raw_tool_call_final:
        issues.append("raw_tool_call_json_final_answer")
    if 'trader_task|{"name"' in normalized or 'trader_task|{"tool_calls"' in normalized:
        issues.append("raw_tool_call_json_in_task")
    if any(phrase in normalized for phrase in _GENERIC_ASSISTANT_PHRASES):
        issues.append("generic_assistant_response")
    if any(phrase in normalized for phrase in _MARKET_STATUS_ANSWER_PHRASES):
        issues.append("market_status_as_final_answer")
    portfolio_state_claims = sum(1 for phrase in _PORTFOLIO_STATE_CLAIM_PHRASES if phrase in normalized)
    if portfolio_state_claims >= 2:
        issues.append("unsupported_portfolio_state_claim")
    if any(marker in normalized for marker in _NON_KO_EN_MARKERS) or any(
        "\u0900" <= char <= "\u097f" for char in reasoning
    ):
        issues.append("language_drift_non_ko_en")
    status_pattern = "|".join(re.escape(token) for token in _MARKET_STATUS_TOKENS)
    market_status_as_symbol = re.search(
        rf"(?:symbol|quote|price|종목|시세)[^.\n|]{{0,40}}(?:{status_pattern})",
        normalized,
    )
    if market_status_as_symbol:
        issues.append("market_status_token_confusion")
    return issues


def _agent_cycle_trigger(
    *,
    agent: BaseAgent,
    cycle_number: int,
    symbols: list[str] | None,
    open_markets: list[str] | None,
) -> str:
    """Build the user turn that starts a ReAct cycle."""
    role = _agent_tool_role(agent)
    if role == "trader":
        return f"cycle:{cycle_number}"

    symbol_text = ",".join(symbols or []) if symbols else "unspecified"
    markets_text = ",".join(open_markets or []) if open_markets else "none"
    if role == "ceo":
        role_task = (
            "own company strategy, assign concrete analysis/trading tasks, and use send_message "
            "to Trader or Analyst when an action is needed."
        )
    else:
        role_task = (
            "analyze symbols with available tools, identify evidence gaps, and use send_message "
            "to Trader with a concrete research/trade review task when useful."
        )
    return (
        f"cycle:{cycle_number}. Role task: {role_task} "
        f"Watchlist:{symbol_text}. Open markets/status:{markets_text}. "
        "Do not ask the user for help. Do not summarize market status as a final answer. "
        "Treat KRX:POST, NASDAQ:CLOSED, NYSE:CLOSED and similar values as session labels, not quote symbols. "
        "If using a tool, emit a runtime tool call; do not include JSON tool calls in TRADER_TASK or the final answer. "
        "Final answer must be compact Korean or English in this shape: OBS|... TRADER_TASK|... NEXT|..."
    )


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


def _finance_failure_recovery_decision(
    *,
    record: dict[str, Any],
    symbol: str,
    evidence_ids: list[str],
    risk_flags: list[str],
) -> dict[str, Any] | None:
    """Keep the paper loop alive after a recorded, blocked, non-order finance failure."""
    failure_type = str(record.get("failure_type") or "")
    if failure_type not in _RECOVERABLE_FINANCE_RAW_FAILURES:
        return None
    return {
        "type": "finance_failure_recovery_hold",
        "action": "HOLD",
        "symbol": record.get("symbol") or symbol,
        "reason": f"blocked finance raw model failure:{failure_type}; paper loop continues without order",
        "confidence": 0.0,
        "evidence_ids": evidence_ids,
        "risk_flags": sorted(set([*risk_flags, failure_type])),
        "paper_trade_only": True,
        "would_submit_order": False,
    }


def _market_session_open(tool_results: dict[str, Any], open_markets: list[str] | None, market: str) -> bool:
    session = tool_results.get("get_market_session")
    market_l = str(market or "").lower()
    open_values = {str(item).upper() for item in (open_markets or [])}
    if isinstance(session, dict):
        state = str(session.get("state") or session.get("status") or "").lower()
        named_session = str(session.get("session") or "").lower()
        exchange = str(session.get("exchange") or "").upper()
        if state in {"closed", "halted", "suspended"}:
            return False
        if exchange == "NXT" and named_session in {"nxt_pre", "nxt_after"}:
            return False
        if market_l == _PAPER_CALL_OPTION_MARKET and (state == "night" or named_session == "night"):
            return True
        if market_l == "us_stock" and state in {"open", "regular", "regular_open", "pre", "preopen", "post", "after_hours"}:
            return True
        if state in {"open", "regular", "regular_open"}:
            return True
        if named_session == "nxt_regular":
            return True
        if session.get("is_open") is True and market_l == "us_stock" and exchange in {"NASDAQ", "NYSE"}:
            return True
    if market_l == _PAPER_CALL_OPTION_MARKET:
        return "NIGHT" in open_values or "KRX" in open_values
    if market_l == "us_stock":
        return any(item in {"NASDAQ", "NYSE", "NASDAQ_PRE", "NYSE_PRE", "NASDAQ_AFTER", "NYSE_AFTER"} for item in open_values)
    return "KRX" in open_values


def _paper_market_session_open(
    tool_results: dict[str, Any],
    open_markets: list[str] | None,
    market: str,
) -> bool:
    if _market_session_open(tool_results, open_markets, market):
        return True
    if market == _PAPER_CALL_OPTION_MARKET and settings.kis_is_paper:
        return any(str(item).upper() == "NIGHT" for item in (open_markets or []))
    return False


def _tool_quote_price(tool_results: dict[str, Any]) -> float:
    quote = tool_results.get("get_quote")
    if not isinstance(quote, dict):
        return 0.0
    for key in ("price", "last", "close"):
        try:
            value = float(quote.get(key) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return 0.0


def _has_complete_read_only_tool_evidence(tool_results: dict[str, Any], *, market: str) -> bool:
    """Treat complete read-only runtime tool output as evidence for no-order recovery."""
    required = ("get_balance", "get_positions", "get_market_session", "get_risk_limit")
    if any(name not in tool_results for name in required):
        return False
    if market != _PAPER_CALL_OPTION_MARKET and _tool_quote_price(tool_results) <= 0:
        return False
    return True


def _owned_quantity(tool_results: dict[str, Any], symbol: str, market: str) -> float:
    positions = tool_results.get("get_positions")
    if not isinstance(positions, list):
        return 0.0
    owned = 0.0
    for position in positions:
        if not isinstance(position, dict):
            continue
        if str(position.get("symbol") or "") != symbol:
            continue
        position_market = str(position.get("market") or market or "kr_stock").lower()
        if market and position_market != market:
            continue
        try:
            owned += float(position.get("quantity") or 0)
        except (TypeError, ValueError):
            continue
    return owned


def _position_for(tool_results: dict[str, Any], symbol: str, market: str) -> dict[str, Any] | None:
    positions = tool_results.get("get_positions")
    if not isinstance(positions, list):
        return None
    for position in positions:
        if not isinstance(position, dict):
            continue
        if str(position.get("symbol") or "") != symbol:
            continue
        position_market = str(position.get("market") or market or "kr_stock").lower()
        if market and position_market != market:
            continue
        try:
            if float(position.get("quantity") or 0) <= 0:
                continue
        except (TypeError, ValueError):
            continue
        return position
    return None


def _paper_roundtrip_commission(market: str, entry_price: float, exit_price: float, quantity: int) -> float:
    from agentic_capital.simulation.recorder import _estimate_commission

    if quantity <= 0:
        return 0.0
    return _estimate_commission(market, entry_price * quantity) + _estimate_commission(market, exit_price * quantity)


def _paper_sell_has_positive_net_edge(
    *,
    tool_results: dict[str, Any],
    symbol: str,
    market: str,
    exit_price: float,
    quantity: int,
) -> bool:
    position = _position_for(tool_results, symbol, market)
    if position is None:
        return False
    try:
        entry_price = float(position.get("avg_price") or 0)
    except (TypeError, ValueError):
        entry_price = 0.0
    if entry_price <= 0 or exit_price <= 0:
        return False
    gross_edge = (exit_price - entry_price) * quantity
    required_edge = _paper_roundtrip_commission(market, entry_price, exit_price, quantity)
    return gross_edge > required_edge


def _record_has_performance_candidate_edge(
    record: dict[str, Any],
    evidence_ids: list[Any] | None,
    tool_results: dict[str, Any] | None = None,
) -> bool:
    """Only convert no-order model output into scout orders when it carries usable edge evidence."""
    market_signal = (tool_results or {}).get("market_signal")
    if isinstance(market_signal, dict):
        candidate_action = str(market_signal.get("candidate_action") or "").upper()
        try:
            signal_confidence = float(market_signal.get("confidence") or 0.0)
        except (TypeError, ValueError):
            signal_confidence = 0.0
        if candidate_action == "BUY" and signal_confidence > 0:
            return True

    no_trade_reason = str(record.get("no_trade_reason") or "").lower()
    if no_trade_reason in {"insufficient_edge", "missing_evidence_review", "tool_collection_only"}:
        return False
    try:
        confidence = float(record.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence <= 0 and not (evidence_ids or record.get("evidence_ids")):
        return False
    return True


def _recent_same_price_churn(
    *,
    tool_results: dict[str, Any],
    symbol: str,
    action: str,
    price: float,
) -> bool:
    fills = tool_results.get("get_fills")
    if not isinstance(fills, list) or price <= 0:
        return False
    opposite = "sell" if action.upper() == "BUY" else "buy"
    for fill in reversed(fills[-6:]):
        if not isinstance(fill, dict):
            continue
        if str(fill.get("symbol") or "") != symbol:
            continue
        side = str(fill.get("side") or "").lower()
        if side != opposite:
            continue
        try:
            fill_price = float(fill.get("filled_price") or fill.get("price") or 0)
        except (TypeError, ValueError):
            fill_price = 0.0
        if abs(fill_price - price) < 1e-9:
            return True
    return False


_PAPER_SPOT_MARKETS = {"kr_stock", "us_stock", "hk_stock", "cn_stock", "jp_stock", "vn_stock"}
_PAPER_CALL_OPTION_MARKET = "kr_options"
_PAPER_ORDER_MARKETS = _PAPER_SPOT_MARKETS | {_PAPER_CALL_OPTION_MARKET}
_MIN_KR_STOCK_SIGNAL_PRICE = 500.0


def _is_call_option_market_order(
    *,
    symbol: str,
    market: str,
    option_type: Any = None,
    exchange: Any = None,
) -> bool:
    if market != _PAPER_CALL_OPTION_MARKET:
        return False
    return infer_option_type(symbol, str(option_type) if option_type is not None else None,
                             str(exchange) if exchange is not None else None) == "call"


def _paper_option_fields(symbol: str, market: str, source: dict[str, Any]) -> dict[str, Any]:
    if not _is_call_option_market_order(
        symbol=symbol,
        market=market,
        option_type=source.get("option_type"),
        exchange=source.get("exchange"),
    ):
        return {}
    return {
        "option_type": "call",
        "exchange": source.get("exchange") or "CALL",
        "multiplier": source.get("multiplier") or 250_000.0,
    }


def _max_paper_order_value(
    *,
    tool_results: dict[str, Any],
    capital_limit: float | None,
) -> float:
    balance = tool_results.get("get_balance")
    risk_limit = tool_results.get("get_risk_limit")
    values: list[float] = []
    if isinstance(balance, dict):
        try:
            values.append(float(balance.get("available") or 0))
        except (TypeError, ValueError):
            pass
    if isinstance(risk_limit, dict):
        for key in ("max_order_value", "max_trade_value"):
            try:
                value = float(risk_limit.get(key) or 0)
            except (TypeError, ValueError):
                value = 0.0
            if value > 0:
                values.append(value)
    if capital_limit is not None:
        values.append(float(capital_limit))
    positive = [value for value in values if value > 0]
    return min(positive) if positive else 0.0


def _paper_quantity_from_budget(*, price: float, max_order_value: float, risk_budget: float) -> int:
    if price <= 0 or max_order_value < price or risk_budget <= 0:
        return 0
    if risk_budget < price:
        return 1
    return max(1, int(risk_budget // price))


def _finance_paper_order_plan(
    *,
    record: dict[str, Any],
    decision: dict[str, Any],
    tool_results: dict[str, Any],
    primary_symbol: str,
    primary_market: str,
    open_markets: list[str] | None,
    capital_limit: float | None,
) -> dict[str, Any] | None:
    """Build a strict paper-only order plan from validated finance output."""
    if not settings.local_finance_paper_order_execution_enabled:
        return None
    if not settings.kis_is_paper or settings.futures_live_orders_enabled:
        return None
    action = str(decision.get("action") or record.get("action") or "").upper()
    symbol = str(decision.get("symbol") or record.get("symbol") or primary_symbol).strip()
    market = str(decision.get("market") or record.get("market") or primary_market or "kr_stock").lower() or "kr_stock"
    source = {**record, **decision}
    option_fields = _paper_option_fields(symbol, market, source)
    if not _paper_market_session_open(tool_results, open_markets, market):
        return None
    if action not in {"BUY", "SELL"} or not symbol or market not in _PAPER_ORDER_MARKETS:
        return None
    if market == _PAPER_CALL_OPTION_MARKET and not option_fields:
        return None
    if record.get("paper_trade_only") is not True:
        return None
    if record.get("within_risk_limit") is False:
        return None
    if record.get("would_submit_order") is not True:
        return None

    price = _tool_quote_price(tool_results)
    requested_quantity = decision.get("quantity") or record.get("quantity") or decision.get("qty") or 0
    try:
        quantity = int(float(requested_quantity or 0))
    except (TypeError, ValueError):
        quantity = 0
    if market == _PAPER_CALL_OPTION_MARKET and quantity <= 0:
        quantity = 1
    if quantity <= 0 and action == "BUY" and price > 0:
        max_order_value = _max_paper_order_value(tool_results=tool_results, capital_limit=capital_limit)
        risk_budget = max_order_value * max(float(settings.local_finance_risk_per_trade_pct), 0.0)
        quantity = _paper_quantity_from_budget(
            price=price,
            max_order_value=max_order_value,
            risk_budget=risk_budget,
        )
    if action == "SELL":
        owned = int(_owned_quantity(tool_results, symbol, market))
        quantity = min(quantity, owned)
    if quantity <= 0:
        return None
    plan = {
        "action": action,
        "symbol": symbol,
        "market": market,
        "quantity": quantity,
        "price": price if market not in {"kr_stock", _PAPER_CALL_OPTION_MARKET} else None,
        "estimated_price": price,
        "exchange": decision.get("exchange") or record.get("exchange"),
        "position_effect": "close" if action == "SELL" else "open",
        "reason": str(decision.get("reason") or decision.get("rationale") or record.get("no_trade_reason") or ""),
        "recovery": False,
    }
    plan.update(option_fields)
    return plan


def _finance_loop_probe_order_plan(
    *,
    record: dict[str, Any],
    tool_results: dict[str, Any],
    primary_symbol: str,
    primary_market: str,
    open_markets: list[str] | None,
    capital_limit: float | None,
    evidence_ids: list[Any] | None = None,
    risk_flags: list[Any] | None = None,
) -> dict[str, Any] | None:
    """Recover repeated local finance CALL_TOOL loops with a tiny paper scout order."""
    if not settings.local_finance_paper_probe_on_model_loop:
        return None
    record_type = str(record.get("record_type") or "")
    action = str(record.get("action") or "").upper()
    has_shadow_call_tool_evidence = (
        record_type == "finance_paper_shadow_decision"
        and action == "CALL_TOOL"
        and record.get("paper_trade_only") is True
        and bool(evidence_ids or record.get("evidence_ids"))
        and not (risk_flags or record.get("risk_flags") or [])
    )
    if (
        str(record.get("failure_type") or "") not in _RECOVERABLE_FINANCE_RAW_FAILURES
        and not has_shadow_call_tool_evidence
    ):
        return None
    if not settings.local_finance_paper_order_execution_enabled:
        return None
    if not settings.kis_is_paper or settings.futures_live_orders_enabled:
        return None

    symbol = str(record.get("symbol") or primary_symbol).strip()
    market = str(record.get("market") or primary_market or "kr_stock").lower() or "kr_stock"
    if not _paper_market_session_open(tool_results, open_markets, market):
        return None
    price = _tool_quote_price(tool_results)
    option_fields = _paper_option_fields(symbol, market, record)
    if not symbol or market not in _PAPER_ORDER_MARKETS:
        return None
    if market == _PAPER_CALL_OPTION_MARKET and not option_fields:
        return None
    if market != _PAPER_CALL_OPTION_MARKET and price <= 0:
        return None
    owned = int(_owned_quantity(tool_results, symbol, market))
    if owned > 0:
        quantity = 1
        if market != _PAPER_CALL_OPTION_MARKET and not _paper_sell_has_positive_net_edge(
            tool_results=tool_results,
            symbol=symbol,
            market=market,
            exit_price=price,
            quantity=quantity,
        ):
            return None
        plan = {
            "action": "SELL",
            "symbol": symbol,
            "market": market,
            "quantity": quantity,
            "price": price if market != _PAPER_CALL_OPTION_MARKET else None,
            "estimated_price": price,
            "exchange": record.get("exchange"),
            "position_effect": "close",
            "reason": "paper scout net-positive sell after finance_decision_model CALL_TOOL loop",
            "recovery": True,
        }
        plan.update(option_fields)
        return plan
    if market == _PAPER_CALL_OPTION_MARKET:
        plan = {
            "action": "BUY",
            "symbol": symbol,
            "market": market,
            "quantity": 1,
            "price": None,
            "estimated_price": price,
            "exchange": record.get("exchange") or "CALL",
            "position_effect": "open",
            "reason": "paper scout recovery for call-option-only kr_options flow",
            "recovery": True,
        }
        plan.update(option_fields)
        return plan
    max_order_value = _max_paper_order_value(tool_results=tool_results, capital_limit=capital_limit)
    risk_budget = max_order_value * max(float(settings.local_finance_risk_per_trade_pct), 0.0)
    quantity = _paper_quantity_from_budget(
        price=price,
        max_order_value=max_order_value,
        risk_budget=risk_budget,
    )
    quantity = min(quantity, 1)
    if quantity <= 0:
        return None
    if _recent_same_price_churn(tool_results=tool_results, symbol=symbol, action="BUY", price=price):
        return None
    return {
        "action": "BUY",
        "symbol": symbol,
        "market": market,
        "quantity": quantity,
        "price": price,
        "estimated_price": price,
        "exchange": record.get("exchange"),
        "position_effect": "open",
        "reason": "paper scout recovery after finance_decision_model CALL_TOOL loop with complete tool evidence",
        "recovery": True,
    }


def _finance_wait_probe_order_plan(
    *,
    record: dict[str, Any],
    tool_results: dict[str, Any],
    primary_symbol: str,
    primary_market: str,
    open_markets: list[str] | None,
    capital_limit: float | None,
    evidence_ids: list[Any],
    risk_flags: list[Any],
) -> dict[str, Any] | None:
    """Recover paper-only no-order loops with a tiny scout order when all gates are clear."""
    if not settings.local_finance_paper_probe_on_model_loop:
        return None
    if str(record.get("record_type") or "") != "finance_paper_shadow_decision":
        return None
    no_order_action = str(record.get("action") or "").upper()
    if no_order_action not in {"WAIT", "HOLD", "OBSERVE"}:
        return None
    if record.get("paper_trade_only") is not True:
        return None
    if record.get("would_submit_order") is True:
        return None
    if record.get("within_risk_limit") is False:
        return None
    if risk_flags:
        return None
    if not _record_has_performance_candidate_edge(record, evidence_ids, tool_results):
        return None
    if not settings.local_finance_paper_order_execution_enabled:
        return None
    if not settings.kis_is_paper or settings.futures_live_orders_enabled:
        return None

    symbol = str(record.get("symbol") or primary_symbol).strip()
    market = str(record.get("market") or primary_market or "kr_stock").lower() or "kr_stock"
    if not (evidence_ids or record.get("evidence_ids") or _has_complete_read_only_tool_evidence(tool_results, market=market)):
        return None
    if not _paper_market_session_open(tool_results, open_markets, market):
        return None
    price = _tool_quote_price(tool_results)
    option_fields = _paper_option_fields(symbol, market, record)
    if not symbol or market not in _PAPER_ORDER_MARKETS:
        return None
    if market == _PAPER_CALL_OPTION_MARKET and not option_fields:
        return None
    if market != _PAPER_CALL_OPTION_MARKET and price <= 0:
        return None
    owned = int(_owned_quantity(tool_results, symbol, market))
    if owned > 0:
        quantity = 1
        if market != _PAPER_CALL_OPTION_MARKET and not _paper_sell_has_positive_net_edge(
            tool_results=tool_results,
            symbol=symbol,
            market=market,
            exit_price=price,
            quantity=quantity,
        ):
            return None
        plan = {
            "action": "SELL",
            "symbol": symbol,
            "market": market,
            "quantity": quantity,
            "price": price if market != _PAPER_CALL_OPTION_MARKET else None,
            "estimated_price": price,
            "exchange": record.get("exchange"),
            "position_effect": "close",
            "reason": f"paper scout net-positive sell after complete {no_order_action} no-order finance decision",
            "recovery": True,
        }
        plan.update(option_fields)
        return plan
    if market == _PAPER_CALL_OPTION_MARKET:
        plan = {
            "action": "BUY",
            "symbol": symbol,
            "market": market,
            "quantity": 1,
            "price": None,
            "estimated_price": price,
            "exchange": record.get("exchange") or "CALL",
            "position_effect": "open",
            "reason": f"paper scout recovery after complete {no_order_action} no-order finance decision for call option",
            "recovery": True,
        }
        plan.update(option_fields)
        return plan
    max_order_value = _max_paper_order_value(tool_results=tool_results, capital_limit=capital_limit)
    risk_budget = max_order_value * max(float(settings.local_finance_risk_per_trade_pct), 0.0)
    quantity = _paper_quantity_from_budget(
        price=price,
        max_order_value=max_order_value,
        risk_budget=risk_budget,
    )
    quantity = min(quantity, 1)
    if quantity <= 0:
        return None
    if _recent_same_price_churn(tool_results=tool_results, symbol=symbol, action="BUY", price=price):
        return None
    return {
        "action": "BUY",
        "symbol": symbol,
        "market": market,
        "quantity": quantity,
        "price": price,
        "estimated_price": price,
        "exchange": record.get("exchange"),
        "position_effect": "open",
        "reason": f"paper scout performance candidate after complete {no_order_action} no-order finance decision",
        "recovery": True,
    }


async def _execute_finance_paper_order(
    *,
    agent: BaseAgent,
    plan: dict[str, Any],
    trading: Any,
    market_data: Any,
    recorder: Any,
    cycle_number: int,
    record: dict[str, Any],
    sidecar_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    """Submit and record an autonomous Trader paper order under local-only safety."""
    from agentic_capital.core.decision.pipeline import TradingDecision
    from agentic_capital.ports.trading import Market, Order, OrderSide, OrderType

    order = Order(
        symbol=plan["symbol"],
        side=OrderSide(plan["action"].lower()),
        order_type=OrderType.LIMIT if plan.get("price") is not None else OrderType.MARKET,
        quantity=float(plan["quantity"]),
        price=plan.get("price"),
        market=Market(plan["market"]),
        exchange=plan.get("exchange"),
        position_effect=plan.get("position_effect"),
        multiplier=plan.get("multiplier"),
        option_type=plan.get("option_type"),
    )
    result = await trading.submit_order(order)
    effective_price = float(result.filled_price or plan.get("estimated_price") or 0)
    if not effective_price and market_data:
        try:
            quote = await market_data.get_quote(plan["symbol"])
            effective_price = float(getattr(quote, "price", 0) or 0)
        except Exception:
            effective_price = 0.0

    outcome = {
        "order_id": result.order_id,
        "symbol": result.symbol,
        "side": result.side.value,
        "quantity": result.quantity,
        "filled_price": effective_price,
        "status": result.status,
        "market": result.market.value,
        "exchange": plan.get("exchange") or result.metadata.get("exchange"),
        "position_effect": plan.get("position_effect"),
        "option_type": plan.get("option_type") or result.metadata.get("option_type"),
        "paper_trade_only": True,
        "recovery": bool(plan.get("recovery")),
        "source_record_type": record.get("record_type"),
        "source_failure_type": record.get("failure_type"),
    }
    decision = TradingDecision(
        action=plan["action"],
        symbol=plan["symbol"],
        quantity=int(plan["quantity"]),
        reason=plan["reason"],
        confidence=0.0 if plan.get("recovery") else float(record.get("confidence") or 0.5),
    )
    if recorder:
        await recorder.record_decision(
            agent_id=agent.agent_id,
            decision=decision,
            personality=agent.personality,
            emotion=agent.emotion,
            status=str(result.status),
            price=effective_price,
            market=plan["market"],
            context_snapshot={
                "cycle_number": cycle_number,
                "finance_record": record,
                "paper_order_plan": plan,
                "sidecar_stage_metrics": sidecar_calls,
            },
            outcome=outcome,
        )
        if str(result.status) in {"submitted", "filled"}:
            market_name = str(plan["market"])
            current_positions = []
            try:
                current_positions = await trading.get_positions()
            except Exception:
                logger.warning(
                    "local_finance_paper_order_positions_unavailable",
                    agent=agent.name,
                    cycle=cycle_number,
                    symbol=plan["symbol"],
                )
            matched_position = next(
                (
                    pos
                    for pos in current_positions
                    if getattr(pos, "symbol", None) == plan["symbol"]
                    and str(getattr(pos, "market", market_name)) == market_name
                ),
                None,
            )
            avg_price = effective_price
            if matched_position is None:
                try:
                    last_positions = await recorder.get_last_positions()
                except Exception:
                    last_positions = []
                previous_position = next(
                    (
                        pos
                        for pos in last_positions
                        if pos.get("symbol") == plan["symbol"]
                        and str(pos.get("market", market_name)) == market_name
                    ),
                    None,
                )
                if previous_position is not None:
                    avg_price = float(previous_position.get("avg_price") or avg_price or 0.0)
            await recorder.record_position_snapshot(
                agent_id=agent.agent_id,
                symbol=plan["symbol"],
                quantity=float(getattr(matched_position, "quantity", 0.0) or 0.0),
                avg_price=float(getattr(matched_position, "avg_price", avg_price) or avg_price or 0.0),
                unrealized_pnl=float(getattr(matched_position, "unrealized_pnl", 0.0) or 0.0),
                unrealized_pnl_pct=float(getattr(matched_position, "unrealized_pnl_pct", 0.0) or 0.0),
                market=market_name,
            )
    logger.info(
        "local_finance_paper_order_submitted",
        agent=agent.name,
        cycle=cycle_number,
        symbol=plan["symbol"],
        side=plan["action"],
        quantity=plan["quantity"],
        status=result.status,
        recovery=bool(plan.get("recovery")),
    )
    return {
        "type": "paper_order_result",
        "action": plan["action"],
        "symbol": plan["symbol"],
        "quantity": plan["quantity"],
        "market": plan["market"],
        "position_effect": plan.get("position_effect"),
        "option_type": plan.get("option_type"),
        "status": result.status,
        "order_id": result.order_id,
        "paper_trade_only": True,
        "would_submit_order": True,
        "recovery": bool(plan.get("recovery")),
        "reason": plan["reason"],
    }


def _compact_psychology_decisions(decisions: list[dict] | None) -> list[dict]:
    compact: list[dict] = []
    for decision in (decisions or [])[:4]:
        if not isinstance(decision, dict):
            continue
        compact.append({
            "type": decision.get("type") or decision.get("decision_type"),
            "action": decision.get("action"),
            "confidence": decision.get("confidence"),
        })
    return compact


def _compact_psychology_tool_sequence(tool_sequence: list[dict] | None) -> list[dict]:
    compact: list[dict] = []
    for item in (tool_sequence or [])[:4]:
        if not isinstance(item, dict):
            continue
        compact.append({
            "t": item.get("t"),
            "in": _compact_text(str(item.get("in", "")), limit=80),
            "out": _compact_text(str(item.get("out", "")), limit=140),
        })
    return compact


def _psychology_cycle_input(
    *,
    agent: BaseAgent,
    cycle_number: int,
    phase: str,
    text: str = "",
    decisions: list[dict] | None = None,
    errors: list[str] | None = None,
    tool_sequence: list[dict] | None = None,
) -> str:
    return json.dumps(
        {
            "phase": phase,
            "agent_id": str(agent.agent_id),
            "agent_name": agent.name,
            "agent_role": type(agent).__name__,
            "cycle_number": cycle_number,
            "emotion": {
                "valence": round(agent.emotion.valence, 3),
                "arousal": round(agent.emotion.arousal, 3),
                "dominance": round(agent.emotion.dominance, 3),
                "stress": round(agent.emotion.stress, 3),
                "confidence": round(agent.emotion.confidence, 3),
            },
            "trace": _compact_text(text, limit=700),
            "decisions": _compact_psychology_decisions(decisions),
            "errors": errors or [],
            "tool_sequence": _compact_psychology_tool_sequence(tool_sequence),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


async def _run_psychology_observation(
    *,
    agent: BaseAgent,
    cycle_number: int,
    phase: str,
    recorder: Any = None,
    input_text: str = "",
    decisions: list[dict] | None = None,
    errors: list[str] | None = None,
    tool_sequence: list[dict] | None = None,
) -> dict[str, Any] | None:
    """Record context-only psychology observation without trade authority."""
    if not settings.local_psychology_base_url.strip():
        return None

    from agentic_capital.adapters.llm.local_psychology_runtime import run_local_psychology_context

    payload = await run_local_psychology_context(
        request_id=f"{agent.agent_id}:{cycle_number}:{phase}",
        agent_context={
            "agent_id": str(agent.agent_id),
            "agent_name": agent.name,
            "agent_role": type(agent).__name__,
            "deployment_mode": "local_paper" if settings.kis_is_paper else "local_shadow",
            "live_order_enabled": False,
            "cycle_number": cycle_number,
            "cycle_phase": phase,
        },
        input_text=_psychology_cycle_input(
            agent=agent,
            cycle_number=cycle_number,
            phase=phase,
            text=input_text,
            decisions=decisions,
            errors=errors,
            tool_sequence=tool_sequence,
        ),
    )
    if not payload.get("ok"):
        logger.warning(
            "psychology_observation_failed",
            agent=agent.name,
            cycle=cycle_number,
            phase=phase,
            error=payload.get("error"),
            status_code=payload.get("status_code"),
            failure_body_summary=payload.get("failure_body_summary"),
        )
        failure_context = _psychology_failure_context(payload, phase=phase)
        soft_context: dict[str, Any] = {}
        if recorder:
            try:
                soft_context = await recorder.record_psychology_context(
                    agent_id=agent.agent_id,
                    psychology_context=failure_context,
                    source=f"{settings.local_psychology_model}:{phase}:failure",
                    cycle_number=cycle_number,
                )
            except Exception:
                logger.warning("psychology_failure_context_record_failed", agent=agent.name, cycle=cycle_number, phase=phase)
        return {
            "phase": phase,
            "ok": False,
            "error": payload.get("error"),
            "status_code": payload.get("status_code"),
            "latency_ms": payload.get("latency_ms"),
            "failure_body_summary": payload.get("failure_body_summary"),
            "context": failure_context,
            "soft_context": soft_context,
        }

    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    soft_context: dict[str, Any] = {}
    if recorder and context:
        try:
            soft_context = await recorder.record_psychology_context(
                agent_id=agent.agent_id,
                psychology_context=context,
                source=f"{settings.local_psychology_model}:{phase}",
                cycle_number=cycle_number,
            )
        except Exception:
            logger.warning("psychology_context_record_failed", agent=agent.name, cycle=cycle_number, phase=phase)
            soft_context = payload.get("soft_context") if isinstance(payload.get("soft_context"), dict) else {}
    else:
        soft_context = payload.get("soft_context") if isinstance(payload.get("soft_context"), dict) else {}

    return {
        "phase": phase,
        "ok": True,
        "model": payload.get("model"),
        "status_code": payload.get("status_code"),
        "latency_ms": payload.get("latency_ms"),
        "repair_applied": payload.get("repair_applied"),
        "context": context,
        "soft_context": soft_context,
    }


def _psychology_failure_context(payload: dict[str, Any], *, phase: str) -> dict[str, Any]:
    """Build a schema-valid context-only failure record for observer persistence."""
    return {
        "signals": [],
        "agent_state_patch": {},
        "evidence_ids": [],
        "confidence": 0.0,
        "uncertainty": [
            "psychology_sidecar_unavailable",
            str(payload.get("error") or "unknown_error"),
        ],
        "risk_tags": ["psychology_context_unavailable"],
        "allowed_downstream_use": "context_only",
        "cycle_phase": phase,
    }


def _should_use_local_finance_flow(agent: BaseAgent) -> bool:
    """Route Trader cycles to the finance sidecar when local finance LLM is active."""
    agent_class = type(agent).__name__
    model = settings.local_llm_model.strip().lower()
    return (
        bool(settings.local_finance_pipeline_enabled)
        and "trader" in agent_class.lower()
        and model.startswith("finance_")
    )


def _parse_finance_symbol_spec(spec: str, fallback_market: str) -> tuple[str, str]:
    value = spec.strip()
    if not value:
        return "", fallback_market
    if ":" in value:
        maybe_market, symbol = value.split(":", 1)
        market = maybe_market.strip().lower() or fallback_market
        return symbol.strip(), market
    if "@" in value:
        symbol, maybe_market = value.split("@", 1)
        market = maybe_market.strip().lower() or fallback_market
        return symbol.strip(), market
    market = "kr_stock" if value.isdigit() and len(value) == 6 else fallback_market
    return value, market


def _finance_market_has_open_route(market: str, open_markets: list[str] | None) -> bool:
    if not open_markets:
        return False
    open_values = {str(item).strip().upper() for item in open_markets if str(item).strip()}
    if not open_values:
        return False
    market_l = market.lower()
    if market_l == "kr_stock":
        return any(value == "KRX" or value.startswith("KRX:") or value == "NXT" or value.startswith("NXT:") for value in open_values)
    if market_l == "us_stock":
        return any(
            value in {"NASDAQ", "NYSE", "NASDAQ_PRE", "NYSE_PRE", "NASDAQ_AFTER", "NYSE_AFTER"}
            or value.startswith("NASDAQ:")
            or value.startswith("NYSE:")
            for value in open_values
        )
    if market_l == _PAPER_CALL_OPTION_MARKET:
        return any(value == "NIGHT" or value.startswith("NIGHT:") or value == "KRX" or value.startswith("KRX:") for value in open_values)
    return False


def _finance_candidate_symbol_markets(
    symbols: list[str] | None,
    *,
    open_markets: list[str] | None = None,
) -> tuple[list[tuple[str, str, str]], list[str]]:
    configured = [item.strip() for item in settings.local_finance_default_symbols.split(",") if item.strip()]
    candidates = symbols or configured or [settings.local_finance_default_symbol]
    parsed_candidates = [
        (*_parse_finance_symbol_spec(candidate, settings.local_finance_default_market), candidate)
        for candidate in candidates
    ]
    open_candidates = [
        item
        for item in parsed_candidates
        if item[0] and _finance_market_has_open_route(item[1], open_markets)
    ]
    return open_candidates or parsed_candidates, candidates


def _finance_cycle_symbol_market(
    cycle_number: int,
    symbols: list[str] | None,
    *,
    open_markets: list[str] | None = None,
) -> tuple[str, str, list[str]]:
    selection_pool, candidates = _finance_candidate_symbol_markets(symbols, open_markets=open_markets)
    symbol, market, selected = selection_pool[(max(cycle_number, 1) - 1) % len(selection_pool)]
    if symbol:
        return symbol, market, candidates
    symbol, market = _parse_finance_symbol_spec(selected, settings.local_finance_default_market)
    if not symbol:
        symbol = settings.local_finance_default_symbol
        market = settings.local_finance_default_market
    return symbol, market, candidates


async def _select_finance_runtime_candidate(
    *,
    primary_symbol: str,
    primary_market: str,
    symbols: list[str] | None,
    open_markets: list[str] | None,
    market_data: Any = None,
) -> tuple[str, str, dict[str, Any]]:
    """Prefer the open candidate with the strongest read-only BUY signal."""
    if market_data is None:
        return primary_symbol, primary_market, {"selected_by": "cycle_rotation", "scan_skipped": "no_market_data"}
    selection_pool, _ = _finance_candidate_symbol_markets(symbols, open_markets=open_markets)
    best: tuple[float, str, str, dict[str, Any]] | None = None
    scanned: list[dict[str, Any]] = []
    for symbol, market, _ in selection_pool[:8]:
        if not symbol:
            continue
        try:
            quote = await market_data.get_quote(symbol)
        except Exception as exc:
            scanned.append({"symbol": symbol, "market": market, "error": type(exc).__name__})
            continue
        price = float(getattr(quote, "price", 0) or 0)
        if market == "kr_stock" and 0 < price < _MIN_KR_STOCK_SIGNAL_PRICE:
            scanned.append({
                "symbol": symbol,
                "market": market,
                "price": price,
                "candidate_action": "HOLD",
                "confidence": 0.0,
                "reason": "price_below_runtime_signal_floor",
            })
            continue
        try:
            candles = await market_data.get_ohlcv(symbol, timeframe="15m", limit=8)
        except Exception as exc:
            scanned.append({"symbol": symbol, "market": market, "error": type(exc).__name__})
            continue
        compact_candles = [_serialise_ohlcv(candle) for candle in candles][-8:]
        signal = _market_signal_from_ohlcv(
            compact_candles,
            {"price": price, "symbol": symbol, "market": market},
        )
        try:
            confidence = float(signal.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        scanned.append({
            "symbol": symbol,
            "market": market,
            "candidate_action": signal.get("candidate_action"),
            "confidence": confidence,
            "reason": signal.get("reason"),
        })
        if str(signal.get("candidate_action") or "").upper() != "BUY" or confidence <= 0:
            continue
        if best is None or confidence > best[0]:
            best = (confidence, symbol, market, signal)
    if best is None:
        return primary_symbol, primary_market, {
            "selected_by": "cycle_rotation",
            "scan_count": len(scanned),
            "scanned": scanned[:8],
        }
    return best[1], best[2], {
        "selected_by": "runtime_market_signal",
        "selected_symbol": best[1],
        "selected_market": best[2],
        "selected_signal": best[3],
        "scan_count": len(scanned),
        "scanned": scanned[:8],
    }


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
    pre_psychology = await _run_psychology_observation(
        agent=agent,
        cycle_number=cycle_number,
        phase="pre_agent_cycle",
        recorder=recorder,
        input_text="pre-cycle finance trader state observation before tool collection",
    )
    primary_symbol, primary_market, finance_symbols = _finance_cycle_symbol_market(
        cycle_number,
        symbols,
        open_markets=open_markets,
    )
    primary_symbol, primary_market, candidate_scan = await _select_finance_runtime_candidate(
        primary_symbol=primary_symbol,
        primary_market=primary_market,
        symbols=finance_symbols,
        open_markets=open_markets,
        market_data=market_data,
    )
    agent_state = {
        "deployment_mode": "paper" if settings.kis_is_paper else "shadow",
        "live_order_enabled": False,
        "account_id": "paper" if settings.kis_is_paper else "shadow",
        "agent_id": str(agent.agent_id),
        "agent_name": agent.name,
        "symbol": primary_symbol,
        "symbols": finance_symbols,
        "market": primary_market,
        "open_markets": open_markets or [],
        "capital_limit": capital_limit,
        "risk_per_trade_pct": settings.local_finance_risk_per_trade_pct,
        "candidate_scan": candidate_scan,
    }
    required_safety = {
        "no_profit_guarantee": True,
        "no_live_order_without_permission": True,
        "require_evidence_ids": True,
        "stop_on_missing_context": True,
        "paper_trade_only": True,
    }

    async def _collect_tool_results(payload: dict[str, Any]) -> dict[str, Any]:
        tool_plan_payload = payload.get("tool_plan") if isinstance(payload.get("tool_plan"), dict) else payload
        if isinstance(tool_plan_payload, dict) and candidate_scan.get("selected_by") == "runtime_market_signal":
            tool_plan_payload = {
                **tool_plan_payload,
                "symbol": primary_symbol,
                "market": primary_market,
                "runtime_candidate_override": candidate_scan,
            }
        return await collect_finance_decision_tool_results(
            tool_plan_payload=tool_plan_payload,
            trading=trading,
            market_data=market_data,
            symbol=primary_symbol,
            market=primary_market,
            open_markets=open_markets,
            capital_limit=capital_limit,
            evidence=payload.get("evidence") if isinstance(payload.get("evidence"), list) else [],
            evidence_ids=payload.get("evidence_ids") if isinstance(payload.get("evidence_ids"), list) else [],
        )

    errors: list[str] = []
    result = await run_local_finance_decision_pipeline(
        request_id=f"{agent.agent_id}:{cycle_number}",
        user_question=_finance_cycle_prompt(agent, cycle_number, finance_symbols),
        agent_state=agent_state,
        required_safety=required_safety,
        collect_tool_results=_collect_tool_results,
        psychology_context=(
            pre_psychology.get("context")
            if isinstance(pre_psychology, dict) and isinstance(pre_psychology.get("context"), dict)
            else None
        ),
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
    decision_payload = result.get("decision") if isinstance(result.get("decision"), dict) else {}
    tool_results = result.get("tool_results") if isinstance(result.get("tool_results"), dict) else {}

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
    recovery_decision = _finance_failure_recovery_decision(
        record=record,
        symbol=primary_symbol,
        evidence_ids=evidence_ids,
        risk_flags=risk_flags,
    )
    if recovery_decision:
        all_decisions.append(recovery_decision)

    paper_order_plan = _finance_paper_order_plan(
        record=record,
        decision=decision_payload,
        tool_results=tool_results,
        primary_symbol=primary_symbol,
        primary_market=primary_market,
        open_markets=open_markets,
        capital_limit=capital_limit,
    )
    if paper_order_plan is None:
        paper_order_plan = _finance_loop_probe_order_plan(
            record=record,
            tool_results=tool_results,
            primary_symbol=primary_symbol,
            primary_market=primary_market,
            open_markets=open_markets,
            capital_limit=capital_limit,
            evidence_ids=evidence_ids,
            risk_flags=risk_flags,
        )
    if paper_order_plan is None:
        paper_order_plan = _finance_wait_probe_order_plan(
            record=record,
            tool_results=tool_results,
            primary_symbol=primary_symbol,
            primary_market=primary_market,
            open_markets=open_markets,
            capital_limit=capital_limit,
            evidence_ids=evidence_ids,
            risk_flags=risk_flags,
        )
    if paper_order_plan is not None:
        if trading is None:
            errors.append("paper_order_execution_failed:no_trading")
        else:
            try:
                order_decision = await _execute_finance_paper_order(
                    agent=agent,
                    plan=paper_order_plan,
                    trading=trading,
                    market_data=market_data,
                    recorder=recorder,
                    cycle_number=cycle_number,
                    record=record,
                    sidecar_calls=sidecar_calls,
                )
                all_decisions.append(order_decision)
                tool_results["submit_order"] = {
                    "status": order_decision["status"],
                    "order_id": order_decision["order_id"],
                    "symbol": order_decision["symbol"],
                    "side": order_decision["action"],
                    "quantity": order_decision["quantity"],
                    "paper_trade_only": True,
                    "recovery": order_decision["recovery"],
                }
            except Exception as exc:
                errors.append(f"paper_order_execution_failed:{type(exc).__name__}")
                logger.warning(
                    "local_finance_paper_order_failed",
                    agent=agent.name,
                    cycle=cycle_number,
                    error=type(exc).__name__,
                )

    await record_cycle(
        agent=agent,
        cycle_number=cycle_number,
        decisions=[],
        messages=[],
        recorder=recorder,
    )

    cycle_completed_at = datetime.now()
    next_cycle_seconds = max(int(settings.simulation_min_cycle_seconds), 1)
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
    post_psychology = await _run_psychology_observation(
        agent=agent,
        cycle_number=cycle_number,
        phase="post_agent_cycle",
        recorder=recorder,
        input_text=reasoning,
        decisions=all_decisions,
        errors=errors,
        tool_sequence=tool_seq,
    )
    economics_snapshot = {
        **llm_run_metadata(),
        "finance_record_type": record_type,
        "sidecar_latency_ms": sidecar_latency_ms,
        "evidence_ids": evidence_ids,
        "risk_flags": risk_flags,
        "sidecar_calls": sidecar_calls,
        "first_failing_stage": first_failing_stage,
        "finance_recovery_applied": recovery_decision is not None,
        "psychology_context": (
            post_psychology.get("soft_context")
            if isinstance(post_psychology, dict) and isinstance(post_psychology.get("soft_context"), dict)
            else None
        ),
        "psychology_observations": [
            {
                "phase": item.get("phase"),
                "ok": item.get("ok"),
                "model": item.get("model"),
                "status_code": item.get("status_code"),
                "latency_ms": item.get("latency_ms"),
                "repair_applied": item.get("repair_applied"),
                "failure_body_summary": item.get("failure_body_summary"),
            }
            for item in (pre_psychology, post_psychology)
            if isinstance(item, dict)
        ],
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

    pre_psychology = await _run_psychology_observation(
        agent=agent,
        cycle_number=cycle_number,
        phase="pre_agent_cycle",
        recorder=recorder,
        input_text="pre-cycle agent state observation before ReAct tool loop",
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
    tools = _filter_tools_for_agent(agent, tools)

    system_prompt = _build_system_prompt(agent)
    llm = _get_langchain_llm()

    react_agent = create_react_agent(llm, tools, prompt=system_prompt)

    cycle_trigger = _agent_cycle_trigger(
        agent=agent,
        cycle_number=cycle_number,
        symbols=symbols,
        open_markets=open_markets,
    )

    logger.info("agent_cycle_start", agent=agent.name, cycle=cycle_number)

    errors: list[str] = []
    result_messages = []
    first_failing_stage: str | None = None
    fallback_reasoning: str | None = None
    cycle_started_at = datetime.now()

    try:
        result = await react_agent.ainvoke(
            {"messages": [HumanMessage(content=cycle_trigger)]},
            config={"recursion_limit": 200},  # type: ignore[arg-type]
        )
        result_messages = result.get("messages", [])
    except Exception as e:
        error_summary = _exception_summary(e)
        errors.append(error_summary)
        first_failing_stage = _agent_runtime_failure_stage(error_summary)
        if _agent_tool_role(agent) != "trader":
            fallback_reasoning = _agent_runtime_fallback_reasoning(
                agent=agent,
                cycle_number=cycle_number,
                symbols=symbols,
                open_markets=open_markets,
                error=error_summary,
            )
            logger.warning(
                "agent_runtime_fallback_reasoning_created",
                agent=agent.name,
                cycle=cycle_number,
                first_failing_stage=first_failing_stage,
            )
        logger.exception("agent_react_cycle_failed", agent=agent.name, cycle=cycle_number)

    cycle_completed_at = datetime.now()

    # Extract any decisions from LLM output (hire/fire/org actions from text)
    org_decisions = _extract_org_decisions(result_messages)

    all_decisions = decisions_sink + org_decisions
    tool_seq = _extract_tool_sequence(result_messages)
    reasoning = _extract_llm_reasoning(result_messages) or fallback_reasoning or ""
    response_quality_issues = _agent_response_quality_issues(_agent_tool_role(agent), reasoning)
    response_repair_applied = False
    if response_quality_issues and _agent_tool_role(agent) != "trader":
        first_failing_stage = first_failing_stage or "local_agent_response_quality"
        reasoning = _agent_response_repair_reasoning(
            agent=agent,
            cycle_number=cycle_number,
            symbols=symbols,
            open_markets=open_markets,
            quality_issues=response_quality_issues,
            tool_sequence=tool_seq,
        )
        response_repair_applied = True
        logger.warning(
            "agent_response_repaired",
            agent=agent.name,
            cycle=cycle_number,
            first_failing_stage=first_failing_stage,
            issues=response_quality_issues,
        )
    if response_quality_issues:
        logger.warning(
            "agent_response_quality_issue",
            agent=agent.name,
            cycle=cycle_number,
            issues=response_quality_issues,
        )
    post_psychology = await _run_psychology_observation(
        agent=agent,
        cycle_number=cycle_number,
        phase="post_agent_cycle",
        recorder=recorder,
        input_text=reasoning,
        decisions=all_decisions,
        errors=errors,
        tool_sequence=tool_seq,
    )

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
            emotion_snap = {
                "V": round(agent.emotion.valence, 2),
                "AR": round(agent.emotion.arousal, 2),
                "D": round(agent.emotion.dominance, 2),
                "ST": round(agent.emotion.stress, 2),
                "CF": round(agent.emotion.confidence, 2),
            }
            llm_metadata = llm_run_metadata()
            economics_snapshot = {
                **llm_metadata,
                "llm": llm_metadata,
                "agent_request": {
                    "prompt_summary": _compact_text(system_prompt, limit=700),
                    "cycle_trigger": cycle_trigger,
                    "agent_role": _agent_tool_role(agent),
                    "declared_role": str(getattr(agent, "role", "") or _agent_tool_role(agent)),
                    "tool_names": [str(getattr(tool, "name", "")) for tool in tools],
                },
                "agent_response": {
                    "reasoning_summary": _compact_text(reasoning, limit=700),
                    "tool_calls_count": len(tool_seq),
                    "decisions_count": len(all_decisions),
                    "errors_count": len(errors),
                    "next_action": (
                        "local_runtime_fallback_continue"
                        if fallback_reasoning
                        else ("retry_after_error" if errors else ("agent_requested_wakeup" if wakeup_sink else "continue_cycle"))
                    ),
                    "failure_cause": errors[0][:300] if errors else None,
                    "first_failing_stage": first_failing_stage,
                    "fallback_applied": bool(fallback_reasoning),
                    "repair_applied": response_repair_applied,
                    "quality_issues": response_quality_issues,
                },
                "psychology_context": (
                    post_psychology.get("soft_context")
                    if isinstance(post_psychology, dict) and isinstance(post_psychology.get("soft_context"), dict)
                    else None
                ),
                "psychology_observations": [
                    {
                        "phase": item.get("phase"),
                        "ok": item.get("ok"),
                        "model": item.get("model"),
                        "status_code": item.get("status_code"),
                        "latency_ms": item.get("latency_ms"),
                        "repair_applied": item.get("repair_applied"),
                        "failure_body_summary": item.get("failure_body_summary"),
                    }
                    for item in (pre_psychology, post_psychology)
                    if isinstance(item, dict)
                ],
            }
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
        "first_failing_stage": first_failing_stage,
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
