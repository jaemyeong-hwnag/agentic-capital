"""Agent tools — account/position queries, market data, and order execution.

System provides: account queries, market data (quote/ohlcv), and trading.
No methodology constraints. No trading restrictions. Only limit: available capital.
"""

from __future__ import annotations

import builtins
import inspect
import re
from typing import Any

import structlog
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

from agentic_capital.config import settings

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Dynamic tool execution sandbox
# ---------------------------------------------------------------------------

_SAFE_BUILTINS: dict = {
    name: getattr(builtins, name)
    for name in [
        "len", "str", "int", "float", "bool", "list", "dict", "tuple", "set",
        "range", "enumerate", "zip", "map", "filter", "min", "max", "sum",
        "abs", "round", "sorted", "reversed", "any", "all", "print", "repr",
        "isinstance", "issubclass", "type", "hasattr", "getattr", "setattr",
        "Exception", "ValueError", "TypeError", "KeyError", "IndexError",
        "AttributeError", "StopIteration", "True", "False", "None",
    ]
    if hasattr(builtins, name)
}

_FORBIDDEN_TOKENS = [
    "import os", "import sys", "import subprocess", "import socket",
    "__import__", "open(", "exec(", "eval(",
]


def _safe_import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):
    """Allow only explicitly approved imports inside AI-created tools."""
    if name == "sqlalchemy" and set(fromlist or ()) <= {"text"}:
        import sqlalchemy
        return sqlalchemy
    raise ImportError(f"import_not_allowed:{name}")


_SAFE_BUILTINS["__import__"] = _safe_import


def _market_key(value: Any) -> str:
    """Normalize market enum/string values for position comparisons."""
    raw = getattr(value, "value", value)
    return str(raw or "").lower()


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_PLACEHOLDER_TEXT = {
    "",
    "agent",
    "agent_name",
    "content",
    "description",
    "name",
    "n/a",
    "na",
    "none",
    "null",
    "order_id",
    "permissions",
    "reason",
    "role",
    "role_name",
    "symbol",
    "target",
    "target_name",
    "ticker",
    "to_agent",
    "type",
    "unknown",
    "unspecified",
}

_MARKET_SESSION_LABELS = {
    "AFTER",
    "AFTER_HOURS",
    "CLOSED",
    "KRX",
    "MARKET_OPEN",
    "NASDAQ",
    "NIGHT",
    "NYSE",
    "OPEN",
    "OPEN_MARKETS",
    "POST",
    "PRE",
    "REGULAR",
}
_MARKET_SESSION_SYMBOL_RE = re.compile(
    r"^[A-Z_]{2,12}:(AFTER|AFTER_HOURS|CLOSED|HALTED|NIGHT|OPEN|POST|PRE|REGULAR|SUSPENDED)$"
)


def _is_placeholder_text(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in _PLACEHOLDER_TEXT or text.startswith("<") or text.endswith("_here")


def _quote_symbol_error(symbol: Any) -> str | None:
    text = str(symbol or "").strip()
    if _is_placeholder_text(text):
        return "placeholder_symbol"
    upper = text.upper()
    if upper in _MARKET_SESSION_LABELS or _MARKET_SESSION_SYMBOL_RE.fullmatch(upper):
        return "market_session_label"
    return None


def _resolve_quote_symbol(primary: Any, fallback: Any = "") -> str:
    for value in (primary, fallback):
        text = str(value or "").strip()
        if text and _quote_symbol_error(text) is None:
            return text
    return str(primary or fallback or "").strip()


def _extract_finance_tool_names(tool_plan_payload: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    candidates = [
        tool_plan_payload.get("tool_plan"),
        tool_plan_payload.get("required_tools"),
        tool_plan_payload.get("tools"),
        tool_plan_payload.get("tool_calls"),
        tool_plan_payload.get("calls"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str):
            names.add(candidate.strip())
        elif isinstance(candidate, list):
            for item in candidate:
                if isinstance(item, str):
                    names.add(item.strip())
                elif isinstance(item, dict):
                    name = item.get("tool") or item.get("name") or item.get("function")
                    if isinstance(name, str):
                        names.add(name.strip())
        elif isinstance(candidate, dict):
            names.update(_extract_finance_tool_names(candidate))
    return {name for name in names if name}


def _symbol_from_plan(tool_plan_payload: dict[str, Any], fallback: str = "") -> str:
    for key in ("symbol", "ticker"):
        value = tool_plan_payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in tool_plan_payload.values():
        if isinstance(value, dict):
            symbol = _symbol_from_plan(value, fallback="")
            if symbol:
                return symbol
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    symbol = _symbol_from_plan(item, fallback="")
                    if symbol:
                        return symbol
    return fallback


def _market_session_from_open_markets(open_markets: list[str] | None, market: str) -> dict[str, Any]:
    market_l = _market_key(market or "kr_stock")
    open_values = {str(item).upper() for item in (open_markets or [])}
    exchange = "KRX" if market_l.startswith("kr_") else "NYSE"
    is_open = exchange in open_values or market_l.upper() in open_values
    return {
        "market": market_l or "kr_stock",
        "exchange": exchange,
        "state": "regular" if is_open else "closed",
        "session": "regular" if is_open else "closed",
        "is_open": is_open,
        "regular_session": is_open,
        "open_markets": sorted(open_values),
    }


def _serialise_position(position: Any) -> dict[str, Any]:
    return {
        "symbol": str(getattr(position, "symbol", "")),
        "quantity": float(getattr(position, "quantity", 0) or 0),
        "avg_price": float(getattr(position, "avg_price", 0) or 0),
        "current_price": float(getattr(position, "current_price", 0) or 0),
        "unrealized_pnl": float(getattr(position, "unrealized_pnl", 0) or 0),
        "unrealized_pnl_pct": float(getattr(position, "unrealized_pnl_pct", 0) or 0),
        "market": _market_key(getattr(position, "market", "")),
        "currency": str(getattr(position, "currency", "")),
    }


def _serialise_balance(balance: Any) -> dict[str, Any]:
    return {
        "total": float(getattr(balance, "total", 0) or 0),
        "available": float(getattr(balance, "available", 0) or 0),
        "currency": str(getattr(balance, "currency", "")),
        "daily_pnl": float(getattr(balance, "daily_pnl", 0) or 0),
        "daily_fee": float(getattr(balance, "daily_fee", 0) or 0),
    }


def _finance_decision_payload(results: dict[str, Any]) -> dict[str, Any]:
    """Return the structure expected by the finance decision sidecar."""
    return {
        "balance": results.get("get_balance", {}),
        "positions": results.get("get_positions", []),
        "quote": results.get("get_quote", {}),
        "market_session": results.get("get_market_session", {}),
        "risk_limit": results.get("get_risk_limit", {}),
        "rag": results.get("search_rag", {}),
        "tool_results": {
            name: results.get(name)
            for name in (
                "search_rag",
                "get_market_session",
                "get_balance",
                "get_positions",
                "get_quote",
                "get_risk_limit",
            )
            if name in results
        },
    }


def _compact_rag_evidence(evidence: list[dict[str, Any]], *, limit: int = 6) -> list[dict[str, Any]]:
    """Keep RAG results model-friendly by stripping full chunk text."""
    compact: list[dict[str, Any]] = []
    for idx, item in enumerate(evidence[:limit]):
        if not isinstance(item, dict):
            continue
        evidence_id = item.get("id") or item.get("evidence_id") or item.get("doc_id") or item.get("chunk_id")
        text = item.get("summary") or item.get("title") or item.get("text") or item.get("content") or ""
        preview = " ".join(str(text).split())
        if len(preview) > 180:
            preview = f"{preview[:180].rstrip()}..."
        compact.append({
            "id": str(evidence_id or f"rag-{idx}"),
            "source": str(item.get("source") or item.get("path") or item.get("doc") or ""),
            "score": item.get("score"),
            "preview": preview,
        })
    return compact


async def collect_finance_decision_tool_results(
    *,
    tool_plan_payload: dict[str, Any],
    trading: Any = None,
    market_data: Any = None,
    symbol: str = "",
    market: str = "kr_stock",
    open_markets: list[str] | None = None,
    capital_limit: float | None = None,
    evidence: list[dict[str, Any]] | None = None,
    evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Collect read-only structured tool results for the local finance sidecar.

    This is separate from LangGraph ReAct text tools. It gives the finance
    decision model deterministic JSON: balance, positions, quote, market
    session, risk limit, and RAG evidence. It never submits orders.
    """
    requested = _extract_finance_tool_names(tool_plan_payload)
    forbidden = sorted(requested & {"submit_order", "submit_live_order", "place_order", "execute_trade"})
    required = {"get_balance", "get_positions", "get_quote", "get_market_session", "get_risk_limit", "search_rag"}
    if not requested:
        requested = set(required)
    requested |= required

    resolved_symbol = _resolve_quote_symbol(_symbol_from_plan(tool_plan_payload, fallback=""), symbol)
    results: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []

    if forbidden:
        errors.append({"tool": "tool_plan", "error": "order_tool_blocked_in_shadow", "tools": forbidden})

    balance_payload: dict[str, Any] = {}
    if "get_balance" in requested:
        if not trading:
            errors.append({"tool": "get_balance", "error": "no_trading"})
        else:
            try:
                balance = await trading.get_balance()
                raw_balance_payload = _serialise_balance(balance)
                total = raw_balance_payload["total"]
                available = raw_balance_payload["available"]
                if capital_limit is not None:
                    total = min(total, float(capital_limit))
                    available = min(available, float(capital_limit))
                balance_payload = {
                    "total": total,
                    "available": available,
                    "currency": raw_balance_payload["currency"],
                    "daily_pnl": raw_balance_payload["daily_pnl"],
                    "daily_fee": raw_balance_payload["daily_fee"],
                    "source": "effective_capital_limit" if capital_limit is not None else "broker",
                }
                inner = getattr(trading, "__dict__", {}).get("_inner")
                if inner is not None and inner is not trading and hasattr(inner, "get_balance"):
                    try:
                        broker_balance = await inner.get_balance()
                        balance_payload["broker_balance"] = _serialise_balance(broker_balance)
                    except Exception:
                        errors.append({"tool": "get_balance.broker_balance", "error": "unavailable"})
                elif capital_limit is not None:
                    balance_payload["broker_balance"] = raw_balance_payload
                results["get_balance"] = balance_payload
            except Exception as exc:
                errors.append({"tool": "get_balance", "error": type(exc).__name__})

    if "get_positions" in requested:
        if not trading:
            errors.append({"tool": "get_positions", "error": "no_trading"})
        else:
            try:
                results["get_positions"] = [_serialise_position(pos) for pos in await trading.get_positions()]
            except Exception as exc:
                errors.append({"tool": "get_positions", "error": type(exc).__name__})

    if "get_quote" in requested:
        if not market_data:
            errors.append({"tool": "get_quote", "error": "no_market_data"})
        elif not resolved_symbol:
            errors.append({"tool": "get_quote", "error": "missing_symbol"})
        elif symbol_error := _quote_symbol_error(resolved_symbol):
            errors.append({"tool": "get_quote", "error": "invalid_symbol", "reason": symbol_error, "symbol": resolved_symbol})
        else:
            try:
                quote = await market_data.get_quote(resolved_symbol)
                results["get_quote"] = {
                    "symbol": str(getattr(quote, "symbol", resolved_symbol)),
                    "price": float(getattr(quote, "price", 0) or 0),
                    "bid": _float_or_none(getattr(quote, "bid", None)),
                    "ask": _float_or_none(getattr(quote, "ask", None)),
                    "volume": _float_or_none(getattr(quote, "volume", None)),
                    "market": str(getattr(quote, "market", market)),
                    "currency": str(getattr(quote, "currency", "")),
                }
            except Exception as exc:
                errors.append({"tool": "get_quote", "error": type(exc).__name__, "symbol": resolved_symbol})

    if "get_market_session" in requested:
        results["get_market_session"] = _market_session_from_open_markets(open_markets, market)

    if "get_risk_limit" in requested:
        available = float(balance_payload.get("available") or 0)
        if capital_limit is not None:
            max_order_value = min(available or float(capital_limit), float(capital_limit))
        else:
            max_order_value = available
        results["get_risk_limit"] = {
            "max_order_value": max_order_value,
            "max_trade_value": max_order_value,
            "capital_limit": float(capital_limit) if capital_limit is not None else None,
            "paper_trade_only": True,
        }

    if "search_rag" in requested:
        ev = evidence or []
        ids = evidence_ids or [
            str(item.get("id") or item.get("evidence_id") or item.get("doc_id") or item.get("chunk_id") or idx)
            for idx, item in enumerate(ev)
            if isinstance(item, dict)
        ]
        results["search_rag"] = {
            "evidence_ids": ids,
            "evidence_count": len(ev),
            "evidence": _compact_rag_evidence(ev),
        }

    if errors:
        results["_errors"] = errors
    results["finance_decision_payload"] = _finance_decision_payload(results)
    results["_meta"] = {
        "requested_tools": sorted(requested),
        "blocked_order_tools": forbidden,
        "symbol": resolved_symbol,
        "market": _market_key(market or "kr_stock"),
    }
    return results


# ---------------------------------------------------------------------------
# Shared position policy — set by CEO/risk_manager, enforced in submit_order
# Persists for the duration of the simulation run (reset on restart)
# ---------------------------------------------------------------------------
_POSITION_POLICY: dict = {
    "max_per_trade_pct": None,   # e.g. 0.30 = max 30% of available per single order
    "max_per_symbol_pct": None,  # e.g. 0.50 = max 50% of total capital in one symbol
    "set_by": None,
    "set_at": None,
}


def _make_tool_namespace(trading: Any, market_data: Any, recorder: Any) -> dict:
    """Restricted execution namespace exposed to AI-created tools."""
    import json
    import math
    from datetime import datetime as _dt

    from sqlalchemy import text

    return {
        "__builtins__": _SAFE_BUILTINS,
        "trading": trading,
        "market_data": market_data,
        "recorder": recorder,
        "json": json,
        "math": math,
        "datetime": _dt,
        "text": text,
    }


def _build_dynamic_tool(
    spec: dict,
    trading: Any,
    market_data: Any,
    recorder: Any,
) -> StructuredTool | None:
    """Exec AI-written tool code and wrap as StructuredTool. Returns None on failure."""
    name = spec["name"]
    description = spec.get("description", "")
    code = spec["code"]

    for token in _FORBIDDEN_TOKENS:
        if token in code:
            logger.warning("dynamic_tool_forbidden_token", name=name, token=token)
            return None

    namespace = _make_tool_namespace(trading, market_data, recorder)
    try:
        exec(code, namespace)
    except Exception as exc:
        logger.warning("dynamic_tool_exec_failed", name=name, error=str(exc))
        return None

    fn = namespace.get(name)
    if not fn or not callable(fn):
        logger.warning("dynamic_tool_fn_not_found", name=name)
        return None

    # Wrap in try/except so dynamic tool failures return ERR: string
    # instead of raising — prevents LangGraph tool node from crashing the cycle
    async def _safe_fn(**kwargs):
        try:
            return await fn(**kwargs)
        except Exception as exc:
            logger.warning("dynamic_tool_exec_error", name=name, error=str(exc))
            return f"ERR:tool_exec:{name}:{exc}"

    # Auto-build Pydantic schema from function signature
    sig = inspect.signature(fn)
    fields: dict = {}
    for pname, param in sig.parameters.items():
        annotation = param.annotation if param.annotation != inspect.Parameter.empty else str
        default = param.default if param.default != inspect.Parameter.empty else ...
        fields[pname] = (annotation, default)

    schema = create_model(f"{name}_schema", **fields) if fields else None

    try:
        return StructuredTool.from_function(
            coroutine=_safe_fn,
            name=name,
            description=description,
            args_schema=schema,
        )
    except Exception as exc:
        logger.warning("dynamic_tool_register_failed", name=name, error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Input schemas for structured tool calling
# ---------------------------------------------------------------------------


class GetFillsInput(BaseModel):
    start_date: str | None = Field(default=None, description="Start date YYYYMMDD")
    end_date: str | None = Field(default=None, description="End date YYYYMMDD")
    symbol: str = Field(default="", description="Filter by symbol (empty = all)")


class SubmitOrderInput(BaseModel):
    symbol: str = Field(description="Ticker symbol to trade")
    side: str = Field(description="Trade direction: buy | sell")
    quantity: float = Field(description="Number of shares/units")
    price: float | None = Field(default=None, description="Limit price (omit for market order)")
    market: str = Field(description="Market you choose: kr_stock (KRX stocks+ETFs+leverage ETFs) | us_stock (NYSE/NASDAQ stocks+ETFs+leveraged ETFs) | kr_futures | kr_options | hk_stock | cn_stock | jp_stock | vn_stock")
    exchange: str | None = Field(default=None, description="Exchange code for overseas (NASD|NYSE|AMEX|SEHK|SHAA|TKSE|HASE)")
    reason: str = Field(default="", description="Trade rationale — why this trade, what signal, what thesis")


class EvaluateReallocationInput(BaseModel):
    buy_symbol: str = Field(description="Candidate buy symbol")
    buy_quantity: float = Field(description="Candidate buy quantity")
    buy_market: str = Field(default="kr_stock", description="Candidate buy market")
    buy_price: float | None = Field(default=None, description="Candidate buy price. Omit to use quote.")
    sell_symbol: str | None = Field(default=None, description="Optional held symbol to sell for funding")
    sell_quantity: float = Field(default=0.0, description="Optional sell quantity from held position")
    sell_market: str = Field(default="kr_stock", description="Sell market")
    sell_price: float | None = Field(default=None, description="Optional sell price. Omit to use quote/current position price.")


class CancelOrderInput(BaseModel):
    order_id: str = Field(description="Order ID to cancel")
    market: str = Field(description="Market: kr_stock | us_stock | kr_futures | kr_options | hk_stock | cn_stock | jp_stock | vn_stock")
    symbol: str = Field(default="", description="Symbol (required for some exchanges)")
    quantity: float = Field(default=0.0, description="Quantity (required for KIS cancel)")


class SaveMemoryInput(BaseModel):
    content: str = Field(description="Memory content to save")
    keywords: list[str] = Field(default_factory=list, description="Keywords for search")


class SearchMemoryInput(BaseModel):
    query: str = Field(description="Search query")
    limit: int = Field(default=5, description="Max results")


class SendMessageInput(BaseModel):
    to_agent: str = Field(description="Target agent name or ID")
    type: str = Field(default="SIG", description="SIG|INSTR|RPT|QRY|ACK|ERR")
    content: str = Field(default="", description="Compact k:v payload e.g. sym:005930,act:BUY,cf:0.87,why:RSI_OS")


class RequestWakeupInput(BaseModel):
    seconds: int = Field(description="Seconds until next cycle. 0=immediately, 3600=1h, 86400=1d")


class GetQuoteInput(BaseModel):
    symbol: str = Field(description="Symbol to quote. KR stocks: 6-digit code (e.g. 005930). US: ticker (e.g. AAPL)")


class GetOHLCVInput(BaseModel):
    symbol: str = Field(description="Symbol. KR: 6-digit code. US: ticker.")
    timeframe: str = Field(default="1d", description="Candle size: 1m|5m|15m|60m|1d|1w|1mo|3mo")
    limit: int = Field(default=20, description="Number of candles to return (max 100)")


class HireAgentInput(BaseModel):
    role: str = Field(description="Agent role: trader | analyst | ceo | risk_manager | quant | researcher (or any custom role)")
    name: str = Field(description="Agent name, e.g. 'Trader-Delta' or 'Quant-Epsilon'")
    capital: float = Field(default=0.0, description="Allocated capital for this agent (0=none)")
    philosophy: str = Field(default="", description="Investment philosophy for this agent")
    personality: dict | None = Field(default=None, description="Optional Big5+PT personality vector: {openness, conscientiousness, extraversion, agreeableness, neuroticism, ...}")


class FireAgentInput(BaseModel):
    target_name: str = Field(description="Name of the agent to fire (exact match)")
    reason: str = Field(description="Reason for termination")


class CreateRoleInput(BaseModel):
    role_name: str = Field(description="New role name in snake_case, e.g. risk_manager")
    description: str = Field(description="What this role does")
    permissions: list[str] = Field(default_factory=list, description="Permissions: trade|analyze|hire|fire|create_role")


class CreateToolInput(BaseModel):
    name: str = Field(description="Tool name in snake_case (e.g. evaluate_agent_pnl)")
    description: str = Field(description="What this tool does and its parameters")
    code: str = Field(
        description=(
            "Complete async Python function. Must define 'async def {name}(...):'.\n"
            "Available in scope: trading, market_data, recorder, json, math, datetime, text\n"
            "Return type must be str (compact AI-friendly format).\n"
            "Forbidden: import os/sys/subprocess/socket, open(), exec(), eval()\n"
            "Example:\n"
            "async def calc_sharpe(agent_id: str, days: int = 7) -> str:\n"
            "    rows = (await recorder._session.execute(\n"
            "        text('SELECT pnl FROM trades WHERE agent_id=:id'), {'id': agent_id}\n"
            "    )).fetchall()\n"
            "    pnls = [r[0] for r in rows]\n"
            "    if not pnls: return 'sharpe:N/A'\n"
            "    avg = sum(pnls) / len(pnls)\n"
            "    std = (sum((x-avg)**2 for x in pnls) / len(pnls)) ** 0.5\n"
            "    sharpe = avg / std if std else 0\n"
            "    return f'sharpe:{sharpe:.2f},n:{len(pnls)}'"
        )
    )


# ---------------------------------------------------------------------------
# Tool builder — creates bound tools for a given agent cycle
# ---------------------------------------------------------------------------


def build_agent_tools(
    *,
    trading: Any = None,
    market_data: Any = None,
    recorder: Any = None,
    agent_id: str = "",
    agent_name: str = "",
    agent_memory: dict | None = None,
    agents_registry: dict | None = None,  # name → agent_id
    preloaded_tools: list | None = None,   # dynamic tools pre-loaded from DB
    capital_limit: float | None = None,    # min(KIS balance, ENV) — company operating cap
) -> tuple:
    """Build LangChain StructuredTools bound to the given adapters.

    Provides: account queries, market data (quote/ohlcv), trading, messaging.
    Returns (tools, decisions_sink, messages_sink, wakeup_sink).
    """
    memory = agent_memory if agent_memory is not None else {}
    decisions_sink: list[dict] = []   # collects all decisions for recording
    messages_sink: list[dict] = []    # collects outbound messages
    wakeup_sink: list[int] = []       # agent-requested next cycle delay (seconds)

    # ---- Account query tools (compact AI-to-AI format) -------------------

    async def get_balance() -> str:
        """Get current account balance (total equity, available cash, currency)."""
        if not trading:
            return "ERR:no_trading"
        try:
            from agentic_capital.formats.compact import bal as _bal
            b = await trading.get_balance()
            # Cap at company operating limit: min(KIS balance, ENV setting)
            # Reflects actual P&L — shrinks on losses, capped on gains
            if capital_limit is not None:
                total = min(b.total, capital_limit)
                available = min(b.available, capital_limit)
            else:
                total, available = b.total, b.available

            # Fetch overseas P&L in KRW (exchange rate already applied by KIS)
            ovs_pnl_krw = 0.0
            if hasattr(trading, "get_overseas_balance"):
                try:
                    ob = await trading.get_overseas_balance("USD")
                    ovs_pnl_krw = ob.daily_pnl  # KRW-converted unrealized PnL
                except Exception:
                    pass

            return _bal(total, available, b.currency, b.daily_pnl, b.daily_fee,
                        ovs_pnl_krw=ovs_pnl_krw)
        except Exception as e:
            return f"ERR:{e}"

    async def get_positions() -> str:
        """Get all open positions with quantity, avg price, unrealized P&L."""
        if not trading:
            return "@pos[0](sym,qty,avg,cur,pnl,pct,mkt,ccy)"
        try:
            from agentic_capital.formats.compact import pos as _pos
            positions = await trading.get_positions()
            return _pos([
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_price": p.avg_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "unrealized_pnl_pct": p.unrealized_pnl_pct,
                    "market": p.market,
                    "currency": p.currency,
                }
                for p in positions
            ])
        except Exception as e:
            return f"ERR:{e}"

    async def get_fills(
        start_date: str | None = None,
        end_date: str | None = None,
        symbol: str = "",
    ) -> str:
        """Get order fill history."""
        if not trading:
            return "@fills[0](oid,sym,sd,qty,px,st)"
        try:
            from agentic_capital.formats.compact import fills as _fills
            from agentic_capital.simulation.recorder import _estimate_commission
            fill_list = await trading.get_fills(start_date=start_date, end_date=end_date, symbol=symbol)
            return _fills([
                {
                    "order_id": f.order_id,
                    "symbol": f.symbol,
                    "side": f.side,
                    "quantity": f.quantity,
                    "filled_price": f.filled_price,
                    "status": f.status,
                    "commission": _estimate_commission(
                        getattr(f, "market", "kr_stock"),
                        (f.filled_price or 0) * (f.quantity or 0),
                    ),
                }
                for f in fill_list
            ])
        except Exception as e:
            return f"ERR:{e}"

    # ---- Trading tools ---------------------------------------------------

    async def submit_order(
        symbol: str,
        side: str,
        quantity: float,
        market: str,
        price: float | None = None,
        exchange: str | None = None,
        reason: str = "",
    ) -> str:
        """Submit a buy or sell order. Returns compact order result."""
        if not trading:
            return "ERR:no_trading"
        try:
            from agentic_capital.formats.compact import order as _order
            from agentic_capital.ports.trading import Market, Order, OrderSide, OrderType

            # Capital hard limit only — the ONLY system-imposed constraint
            # Position policy is AI-decided and informational only (not enforced here)
            side_l = side.lower()
            market_l = market.lower()
            if settings.kis_is_paper and market_l in {"us_stock", "hk_stock", "cn_stock", "jp_stock", "vn_stock"}:
                return (
                    "ERR:paper_no_overseas|KIS_IS_PAPER=true blocks overseas orders|"
                    "use kr_stock or futures paper tools, or switch to explicit real mode"
                )
            if side_l == "sell" and market_l in {"kr_stock", "us_stock", "hk_stock", "cn_stock", "jp_stock", "vn_stock"}:
                positions = await trading.get_positions()
                owned_qty = sum(
                    float(getattr(p, "quantity", 0) or 0)
                    for p in positions
                    if getattr(p, "symbol", "") == symbol and _market_key(getattr(p, "market", "")) == market_l
                )
                if quantity > owned_qty:
                    return (
                        f"ERR:insufficient_position|"
                        f"sym:{symbol}|have:{owned_qty:.8g}|sell:{quantity:.8g}|max_qty:{owned_qty:.8g}"
                    )

            if side_l == "buy":
                risk_price = price
                if (risk_price is None or risk_price <= 0) and market_data:
                    try:
                        q = await market_data.get_quote(symbol)
                        risk_price = q.price
                    except Exception:
                        risk_price = None
                if risk_price is None or risk_price <= 0:
                    return "ERR:price_required_for_buy_risk_check"

                order_value = risk_price * quantity
                b = await trading.get_balance()
                effective_available = min(b.available, capital_limit) if capital_limit else b.available

                if order_value > effective_available:
                    return (
                        f"ERR:insufficient_capital|"
                        f"need:{order_value:.0f}|avl:{effective_available:.0f}|"
                        f"max_qty:{int(effective_available // risk_price)}"
                    )

            o = Order(
                symbol=symbol,
                side=OrderSide(side_l),
                order_type=OrderType.LIMIT if price is not None else OrderType.MARKET,
                quantity=quantity,
                price=price,
                market=Market(market),
                exchange=exchange,
            )
            result = await trading.submit_order(o)

            # For market orders KIS paper API returns filled_price=0.
            # Fall back to current quote price as best estimate.
            effective_price = price or result.filled_price
            if not effective_price and market_data:
                try:
                    q = await market_data.get_quote(symbol)
                    effective_price = q.price
                except Exception:
                    pass

            from agentic_capital.simulation.recorder import _estimate_commission
            trade_value = effective_price * result.quantity if effective_price else 0
            commission = _estimate_commission(market, trade_value)
            outcome = {
                "order_id": result.order_id,
                "symbol": result.symbol,
                "side": result.side,
                "quantity": result.quantity,
                "filled_price": effective_price,
                "status": result.status,
                "market": result.market,
                "commission": commission,
            }

            decisions_sink.append({
                "type": "trade",
                "action": side.upper(),
                "symbol": symbol,
                "quantity": quantity,
                "price": effective_price,
                "market": market,
                "exchange": exchange,
                "order_id": result.order_id,
                "status": result.status,
                "commission": commission,
                "reason": reason,  # AI-provided trade rationale
            })

            logger.info(
                "agent_order_submitted",
                agent=agent_name,
                symbol=symbol,
                side=side,
                quantity=quantity,
                status=result.status,
            )
            return _order(outcome)
        except Exception as e:
            logger.exception("agent_submit_order_failed", agent=agent_name, symbol=symbol)
            return f"ERR:{e}"

    async def evaluate_reallocation(
        buy_symbol: str,
        buy_quantity: float,
        buy_market: str = "kr_stock",
        buy_price: float | None = None,
        sell_symbol: str | None = None,
        sell_quantity: float = 0.0,
        sell_market: str = "kr_stock",
        sell_price: float | None = None,
    ) -> str:
        """Estimate cash gap and friction for SELL+BUY reallocation without placing orders."""
        if not trading:
            return "ERR:no_trading"
        try:
            from agentic_capital.simulation.recorder import _estimate_commission

            balance = await trading.get_balance()
            available = min(balance.available, capital_limit) if capital_limit else balance.available
            positions = await trading.get_positions()

            def _position(symbol: str, market: str):
                for p in positions:
                    if getattr(p, "symbol", "") == symbol and _market_key(getattr(p, "market", "")) == market:
                        return p
                return None

            async def _price(symbol: str, fallback: float | None) -> float | None:
                if fallback and fallback > 0:
                    return fallback
                pos = _position(symbol, buy_market if symbol == buy_symbol else sell_market)
                if pos and getattr(pos, "current_price", 0):
                    return float(pos.current_price)
                if market_data:
                    try:
                        q = await market_data.get_quote(symbol)
                        return float(q.price)
                    except Exception:
                        return None
                return None

            buy_px = await _price(buy_symbol, buy_price)
            if buy_px is None or buy_px <= 0:
                return "ERR:buy_price_required"

            buy_value = buy_px * buy_quantity
            buy_fee = _estimate_commission(buy_market, buy_value)

            sell_value = 0.0
            sell_fee = 0.0
            sell_have = 0.0
            if sell_symbol and sell_quantity > 0:
                sell_pos = _position(sell_symbol, sell_market)
                sell_have = float(getattr(sell_pos, "quantity", 0) or 0)
                if sell_quantity > sell_have:
                    return (
                        f"ERR:insufficient_position|sym:{sell_symbol}|"
                        f"have:{sell_have:.8g}|sell:{sell_quantity:.8g}|max_qty:{sell_have:.8g}"
                    )
                sell_px = await _price(sell_symbol, sell_price)
                if sell_px is None or sell_px <= 0:
                    return "ERR:sell_price_required"
                sell_value = sell_px * sell_quantity
                sell_fee = _estimate_commission(sell_market, sell_value)

            cash_after_sell = available + sell_value - sell_fee
            buy_total_cost = buy_value + buy_fee
            cash_gap = max(0.0, buy_total_cost - cash_after_sell)
            friction = buy_fee + sell_fee
            net_cash_after = cash_after_sell - buy_total_cost
            action = "funded" if cash_gap <= 0 else "need_more_cash_or_smaller_buy"
            if not sell_symbol and cash_gap > 0:
                action = "evaluate_selling_positions_or_wait"
            return (
                f"realloc:{action}|buy:{buy_symbol},{buy_quantity:.8g}@{buy_px:.0f},cost:{buy_total_cost:.0f}|"
                f"sell:{sell_symbol or ''},{sell_quantity:.8g},proceeds:{sell_value:.0f}|"
                f"avl:{available:.0f}|gap:{cash_gap:.0f}|net_cash_after:{net_cash_after:.0f}|"
                f"friction:{friction:.0f}|min_expected_edge_gt:{friction:.0f}"
            )
        except Exception as e:
            logger.exception("agent_evaluate_reallocation_failed", agent=agent_name)
            return f"ERR:{e}"

    async def cancel_order(
        order_id: str,
        market: str,
        symbol: str = "",
        quantity: float = 0.0,
    ) -> str:
        """Cancel a pending order."""
        if not trading:
            return "ERR:no_trading"
        try:
            success = await trading.cancel_order(order_id, symbol=symbol, quantity=quantity, market=market)
            return f"cancelled:{success},oid:{order_id}"
        except Exception as e:
            return f"ERR:{e}"

    # ---- Memory tools ----------------------------------------------------

    async def save_memory(content: str, keywords: list[str] | None = None) -> str:
        """Save a memory entry for future reference."""
        import time
        entry = {
            "content": content,
            "keywords": keywords or [],
            "timestamp": time.time(),
        }
        key = f"mem_{len(memory)}"
        memory[key] = entry
        return f"saved:1,key:{key}"

    async def search_memory(query: str, limit: int = 5) -> str:
        """Search agent memory by keyword or content match."""
        from agentic_capital.formats.compact import mem_entries
        query_lower = query.lower()
        results = []
        for entry in memory.values():
            content = entry.get("content", "").lower()
            kws = [k.lower() for k in entry.get("keywords", [])]
            if query_lower in content or any(query_lower in k for k in kws):
                results.append(entry)
            if len(results) >= limit:
                break
        return mem_entries(results)

    # ---- Messaging tools -------------------------------------------------

    async def send_message(to_agent: str, type: str = "SIG", content: str = "") -> str:
        """Send a compact message to another agent.

        content: compact k:v pairs e.g. "sym:005930,act:BUY,cf:0.87,why:RSI_OS"
        Full wire format: TYPE|FROM|TO|TS|content
        """
        if _is_placeholder_text(to_agent) or _is_placeholder_text(type) or _is_placeholder_text(content):
            return "ERR:placeholder_message"

        from agentic_capital.formats.compact import msg_encode
        wire = msg_encode(type, agent_name, to_agent, content)
        msg = {
            "from": agent_name,
            "to": to_agent,
            "type": type,
            "content": content,
            "wire": wire,
        }
        messages_sink.append(msg)
        logger.info("agent_message_sent", from_agent=agent_name, to=to_agent, type=type)
        return "sent:1"

    # ---- Market data tools -----------------------------------------------

    async def get_quote(symbol: str) -> str:
        """Get current price quote. KR stocks: 6-digit code (005930). US: ticker (AAPL)."""
        if not market_data:
            return "ERR:no_market_data"
        resolved_symbol = _resolve_quote_symbol(symbol)
        if error := _quote_symbol_error(resolved_symbol):
            return f"ERR:invalid_symbol:{error}:{resolved_symbol}"
        try:
            from agentic_capital.formats.compact import quote as _quote
            q = await market_data.get_quote(resolved_symbol)
            return _quote(q.symbol, q.price, q.bid, q.ask, q.volume, q.currency)
        except Exception as e:
            return f"ERR:{e}"

    async def get_ohlcv(symbol: str, timeframe: str = "1d", limit: int = 20) -> str:
        """Get historical OHLCV candles. Returns TOON table. timeframe: 1m|5m|15m|60m|1d|1w|1mo|3mo"""
        if not market_data:
            return "ERR:no_market_data"
        resolved_symbol = _resolve_quote_symbol(symbol)
        if error := _quote_symbol_error(resolved_symbol):
            return f"ERR:invalid_symbol:{error}:{resolved_symbol}"
        try:
            from agentic_capital.formats.compact import ohlcv as _ohlcv
            candles = await market_data.get_ohlcv(resolved_symbol, timeframe=timeframe, limit=limit)
            return _ohlcv(resolved_symbol, candles)
        except Exception as e:
            return f"ERR:{e}"

    # ---- Market status ---------------------------------------------------

    async def get_market_status() -> str:
        """Query real-time market session state across major exchanges.

        Returns current session state per market:
          REGULAR  = regular trading hours
          PRE      = pre-market (04:00-09:30 ET / 17:00-22:30 KST)
          POST     = after-hours (16:00-20:00 ET / 05:00-09:00 KST next day)
          CLOSED   = closed (weekend, holiday, or outside all sessions)
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo

        import yfinance as yf

        kst = ZoneInfo("Asia/Seoul")
        et = ZoneInfo("America/New_York")  # DST-aware

        # yfinance raw -> normalized state
        # PREPRE = before pre-market opens (01:00-04:00 ET) -> not tradeable
        # POSTPOST = very late after-hours -> treat same as POST
        def _normalize(raw: str) -> str:
            return {"PREPRE": "CLOSED", "POSTPOST": "POST"}.get(raw, raw)

        checks = [
            ("KRX",    "^KS11",  kst),
            ("NASDAQ", "^IXIC",  et),
            ("NYSE",   "^GSPC",  et),
        ]
        results = []
        for market, sym, tz in checks:
            local_time = datetime.now(tz).strftime("%H:%M")
            try:
                info = yf.Ticker(sym).info
                state = _normalize(info.get("marketState", "CLOSED"))
                results.append(f"{market}:{state}@{local_time}")
            except Exception:
                results.append(f"{market}:ERR@{local_time}")
        return "|".join(results)

    # ---- Position policy tools (CEO/risk_manager) ------------------------

    async def set_position_policy(
        max_per_trade_pct: float,
        max_per_symbol_pct: float = 1.0,
    ) -> str:
        """Set position sizing policy. Applies to ALL agents immediately.

        max_per_trade_pct: max fraction of available capital per single order (e.g. 0.3 = 30%)
        max_per_symbol_pct: max fraction of total capital in one symbol (e.g. 0.5 = 50%)

        Example: set_position_policy(0.2, 0.4) → each trade ≤20% of cash, each symbol ≤40% total
        """
        import time
        max_per_trade_pct = max(0.01, min(1.0, max_per_trade_pct))
        max_per_symbol_pct = max(0.01, min(1.0, max_per_symbol_pct))
        _POSITION_POLICY["max_per_trade_pct"] = max_per_trade_pct
        _POSITION_POLICY["max_per_symbol_pct"] = max_per_symbol_pct
        _POSITION_POLICY["set_by"] = agent_name
        _POSITION_POLICY["set_at"] = time.strftime("%H:%M")
        logger.info(
            "position_policy_set",
            by=agent_name,
            max_per_trade_pct=max_per_trade_pct,
            max_per_symbol_pct=max_per_symbol_pct,
        )
        return (
            f"policy_set|max_per_trade:{max_per_trade_pct:.0%}|"
            f"max_per_symbol:{max_per_symbol_pct:.0%}|"
            f"effective:immediately|applies_to:all_agents"
        )

    async def get_position_policy() -> str:
        """Get current position sizing policy set by CEO/risk_manager."""
        pct = _POSITION_POLICY.get("max_per_trade_pct")
        sym = _POSITION_POLICY.get("max_per_symbol_pct")
        by = _POSITION_POLICY.get("set_by", "none")
        if pct is None:
            return "policy:none|no_limit_set|set_by:none"
        return f"max_per_trade:{pct:.0%}|max_per_symbol:{sym:.0%}|set_by:{by}"

    # ---- HR tools (CEO-accessible) ---------------------------------------

    async def hire_agent(
        role: str,
        name: str,
        capital: float = 0.0,
        philosophy: str = "",
        personality: dict | None = None,
    ) -> str:
        """Hire a new agent. CEO decides role, name, capital allocation, philosophy."""
        if _is_placeholder_text(role) or _is_placeholder_text(name):
            return "ERR:placeholder_hr_decision"

        decision = {
            "type": "hire",
            "role": role,
            "target": name,
            "capital": capital,
            "reason": philosophy,
            "personality": personality or {},
        }
        decisions_sink.append(decision)
        logger.info("hr_hire_requested", by=agent_name, role=role, name=name, capital=capital)
        return f"hire_queued:name={name},role={role},capital={capital:.0f}"

    async def fire_agent(target_name: str, reason: str) -> str:
        """Fire an existing agent by name. CEO decides who and why."""
        if _is_placeholder_text(target_name) or _is_placeholder_text(reason):
            return "ERR:placeholder_hr_decision"

        decision = {
            "type": "fire",
            "target": target_name,
            "reason": reason,
        }
        decisions_sink.append(decision)
        logger.info("hr_fire_requested", by=agent_name, target=target_name)
        return f"fire_queued:target={target_name}"

    async def create_role(role_name: str, description: str, permissions: list[str] | None = None) -> str:
        """Create a new organizational role with defined permissions."""
        if _is_placeholder_text(role_name) or _is_placeholder_text(description):
            return "ERR:placeholder_hr_decision"
        if any(_is_placeholder_text(permission) for permission in (permissions or [])):
            return "ERR:placeholder_hr_decision"

        decision = {
            "type": "create_role",
            "detail": role_name,
            "target": role_name,
            "reason": description,
            "permissions": permissions or [],
        }
        decisions_sink.append(decision)
        logger.info("hr_create_role_requested", by=agent_name, role=role_name)
        return f"role_queued:{role_name}"

    # ---- Dynamic tool creation -------------------------------------------

    async def create_tool(name: str, description: str, code: str) -> str:
        """AI creates a new persistent tool. Available from the next cycle for ALL agents.

        The tool code runs in a restricted sandbox with access to:
        trading, market_data, recorder, json, math, datetime.
        Forbidden: os, sys, subprocess, socket, open, exec, eval.
        """
        for token in _FORBIDDEN_TOKENS:
            if token in code:
                return f"ERR:forbidden_token:{token}"

        # Compile check before saving
        try:
            compile(code, "<dynamic>", "exec")
        except SyntaxError as exc:
            return f"ERR:syntax:{exc}"

        # Quick exec test in sandbox to catch runtime errors
        test_ns = _make_tool_namespace(trading, market_data, recorder)
        try:
            exec(code, test_ns)
        except Exception as exc:
            return f"ERR:exec:{exc}"

        fn = test_ns.get(name)
        if not fn or not callable(fn):
            return f"ERR:fn_not_found — function must be named '{name}'"

        if recorder:
            try:
                from uuid import UUID
                creator = UUID(agent_id) if agent_id else None
                await recorder.save_tool(name, description, code, created_by=creator)
            except Exception as exc:
                return f"ERR:save:{exc}"

        logger.info("agent_tool_created", creator=agent_name, name=name)
        return f"OK:tool_created:{name}|available_next_cycle|all_agents_can_use"

    # ---- Timing control --------------------------------------------------

    async def request_wakeup(seconds: int) -> str:
        """Schedule next wakeup and END this cycle. Call this ONCE when done.

        After calling this, stop all tool calls and return your final response.
        Do NOT call this multiple times — only the first call is used.

        seconds=60: market OPEN, actively trading
        seconds=300: market open, monitoring
        seconds=1800: market open, low activity
        seconds=3600: 1 hour

        IMPORTANT: KR market 09:00-15:30 KST | US pre-market 17:00 KST | US regular 22:30 KST
        Sleep no more than until the NEXT market session opens.
        If KR closing soon (e.g. 15:20 KST) → sleep until US pre-market (17:00 KST) = ~5400s
        Between US sessions → max 3600s
        Never miss a session: KR or US pre/regular/after-hours all offer profit opportunities.
        """
        capped = min(max(0, seconds), 7200)
        if not wakeup_sink:  # only first call counts
            wakeup_sink.append(capped)
        logger.info("agent_wakeup_requested", agent=agent_name, seconds=seconds)
        return f"CYCLE_DONE. Next wakeup in {capped}s. Stop here — do not call any more tools."

    # ---- Build tool list -----------------------------------------------

    tools = [
        StructuredTool.from_function(
            coroutine=get_balance,
            name="get_balance",
            description="Get current account balance (total equity, available cash, currency)",
        ),
        StructuredTool.from_function(
            coroutine=get_positions,
            name="get_positions",
            description="Get all open positions with quantity, avg price, unrealized P&L",
        ),
        StructuredTool.from_function(
            coroutine=get_fills,
            name="get_fills",
            description="Get order fill history for review",
            args_schema=GetFillsInput,
        ),
        StructuredTool.from_function(
            coroutine=submit_order,
            name="submit_order",
            description=(
                "Submit a buy or sell order. You decide market, symbol, quantity, and price. "
                "In KIS paper mode, overseas stock markets are blocked; use kr_stock or futures paper tools. "
                "If cash is insufficient, first use evaluate_reallocation to compare HOLD vs SELL+BUY; "
                "spot sell orders are limited to owned quantity."
            ),
            args_schema=SubmitOrderInput,
        ),
        StructuredTool.from_function(
            coroutine=evaluate_reallocation,
            name="evaluate_reallocation",
            description=(
                "Estimate cash gap, sale proceeds, buy cost, and friction for selling a held asset "
                "to fund a better expected trade. This does not place orders. Use before SELL+BUY "
                "when available cash is low or capital is locked in positions."
            ),
            args_schema=EvaluateReallocationInput,
        ),
        StructuredTool.from_function(
            coroutine=cancel_order,
            name="cancel_order",
            description="Cancel a pending order by order ID",
            args_schema=CancelOrderInput,
        ),
        StructuredTool.from_function(
            coroutine=save_memory,
            name="save_memory",
            description="Save analysis, observations, or decisions to memory for future cycles",
            args_schema=SaveMemoryInput,
        ),
        StructuredTool.from_function(
            coroutine=search_memory,
            name="search_memory",
            description="Search previous memories by keyword",
            args_schema=SearchMemoryInput,
        ),
        StructuredTool.from_function(
            coroutine=send_message,
            name="send_message",
            description="Send a message (signal, instruction, report) to another agent",
            args_schema=SendMessageInput,
        ),
        StructuredTool.from_function(
            coroutine=get_quote,
            name="get_quote",
            description="Get current price quote for any symbol. KR stocks/ETFs: 6-digit code (e.g. 005930, 069500). US stocks/ETFs: ticker (e.g. AAPL, SPY, TQQQ, SOXL).",
            args_schema=GetQuoteInput,
        ),
        StructuredTool.from_function(
            coroutine=get_ohlcv,
            name="get_ohlcv",
            description="Get historical OHLCV price candles for technical analysis. timeframe: 1d|60m|15m|5m|1w|1mo",
            args_schema=GetOHLCVInput,
        ),
        StructuredTool.from_function(
            coroutine=request_wakeup,
            name="request_wakeup",
            description="Control when this agent runs next. Agent decides its own cycle timing.",
            args_schema=RequestWakeupInput,
        ),
        StructuredTool.from_function(
            coroutine=get_market_status,
            name="get_market_status",
            description=(
                "Query real-time market session state per exchange. "
                "Returns REGULAR|PRE|POST|CLOSED with local exchange time. "
                "PRE = pre-market (04:00-09:30 ET), POST = after-hours (16:00-20:00 ET)."
            ),
        ),
        StructuredTool.from_function(
            coroutine=create_tool,
            name="create_tool",
            description=(
                "Create a new persistent tool that YOU and all other agents can use from the next cycle. "
                "Use this to build capabilities the system doesn't provide: "
                "HR evaluation, performance metrics, risk calculators, portfolio analyzers, "
                "hiring criteria checkers, strategy backtests — anything you need. "
                "Tools persist across simulations and compound over time."
            ),
            args_schema=CreateToolInput,
        ),
        StructuredTool.from_function(
            coroutine=set_position_policy,
            name="set_position_policy",
            description=(
                "Record position sizing policy (max % per trade, per symbol). "
                "Other agents can read this via get_position_policy to self-regulate. "
                "Example: set_position_policy(0.2) → max_per_trade=20% of capital."
            ),
        ),
        StructuredTool.from_function(
            coroutine=get_position_policy,
            name="get_position_policy",
            description="Get current position sizing policy (max % per trade, set by whom).",
        ),
        StructuredTool.from_function(
            coroutine=hire_agent,
            name="hire_agent",
            description=(
                "Hire a new agent. You decide: role (trader/analyst/quant/risk_manager/researcher/any), "
                "name, capital allocation, philosophy, and optional personality vector. "
                "Agent is created immediately and runs in the next cycle."
            ),
            args_schema=HireAgentInput,
        ),
        StructuredTool.from_function(
            coroutine=fire_agent,
            name="fire_agent",
            description=(
                "Fire (terminate) an agent by name. You decide who and why. "
                "Agent is removed from the roster immediately after this cycle."
            ),
            args_schema=FireAgentInput,
        ),
        StructuredTool.from_function(
            coroutine=create_role,
            name="create_role",
            description=(
                "Define a new organizational role with a name and permissions. "
                "Use this to structure the organization before hiring into that role."
            ),
            args_schema=CreateRoleInput,
        ),
    ]

    # Inject pre-loaded AI-created tools (built from DB before this call)
    for dynamic_tool in (preloaded_tools or []):
        if dynamic_tool is not None:
            tools.append(dynamic_tool)

    return tools, decisions_sink, messages_sink, wakeup_sink


# ---------------------------------------------------------------------------
# Legacy class — kept for backward compatibility
# ---------------------------------------------------------------------------


class DataQueryTools:
    """Legacy data query class for backward compatibility.

    New code should use build_agent_tools() directly.
    """

    def __init__(self, *, trading: Any = None, market_data: Any = None, recorder: Any = None) -> None:
        self._trading = trading
        self._market_data = market_data
        self._recorder = recorder

    async def query_balance(self) -> dict:
        """Query current account balance."""
        if not self._trading:
            return {"error": "trading adapter not available"}
        try:
            bal = await self._trading.get_balance()
            return {"total": bal.total, "available": bal.available, "currency": bal.currency}
        except Exception as e:
            logger.warning("query_balance_failed", error=str(e))
            return {"error": str(e)}

    async def query_positions(self) -> list[dict]:
        """Query all open positions."""
        if not self._trading:
            return []
        try:
            positions = await self._trading.get_positions()
            return [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_price": p.avg_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "unrealized_pnl_pct": p.unrealized_pnl_pct,
                }
                for p in positions
            ]
        except Exception as e:
            logger.warning("query_positions_failed", error=str(e))
            return []

    async def query_quote(self, symbol: str) -> dict:
        """Query current price quote for a symbol."""
        if not self._market_data:
            return {"error": "market data adapter not available"}
        resolved_symbol = _resolve_quote_symbol(symbol)
        if error := _quote_symbol_error(resolved_symbol):
            return {"error": f"invalid_symbol:{error}", "symbol": resolved_symbol}
        try:
            quote = await self._market_data.get_quote(resolved_symbol)
            return {
                "symbol": resolved_symbol,
                "price": quote.price,
                "bid": quote.bid,
                "ask": quote.ask,
                "volume": quote.volume,
            }
        except Exception as e:
            logger.warning("query_quote_failed", symbol=symbol, error=str(e))
            return {"error": str(e)}

    async def query_quotes(self, symbols: list[str]) -> list[dict]:
        """Query quotes for multiple symbols."""
        results = []
        for symbol in symbols:
            result = await self.query_quote(symbol)
            if "error" not in result:
                results.append(result)
        return results

    async def query_ohlcv(self, symbol: str, timeframe: str = "1d", limit: int = 30) -> list[dict]:
        """Query historical OHLCV candles."""
        if not self._market_data:
            return []
        resolved_symbol = _resolve_quote_symbol(symbol)
        if error := _quote_symbol_error(resolved_symbol):
            logger.warning("query_ohlcv_invalid_symbol", symbol=resolved_symbol, reason=error)
            return []
        try:
            candles = await self._market_data.get_ohlcv(resolved_symbol, timeframe=timeframe, limit=limit)
            return [
                {
                    "timestamp": str(c.timestamp),
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                }
                for c in candles
            ]
        except Exception as e:
            logger.warning("query_ohlcv_failed", symbol=symbol, error=str(e))
            return []

    async def query_symbols(self) -> list[str]:
        """Query all available trading symbols."""
        if not self._market_data:
            return []
        try:
            return await self._market_data.get_symbols()
        except Exception as e:
            logger.warning("query_symbols_failed", error=str(e))
            return []

    def get_tool_descriptions(self) -> list[dict]:
        """Return tool descriptions for LLM function calling."""
        return [
            {"name": "query_balance", "description": "Get current account balance", "parameters": {}},
            {"name": "query_positions", "description": "Get all open positions with P&L", "parameters": {}},
            {"name": "query_quote", "description": "Get current price for a symbol", "parameters": {"symbol": "string"}},
            {"name": "query_quotes", "description": "Get current prices for multiple symbols", "parameters": {"symbols": "list[string]"}},
            {"name": "query_ohlcv", "description": "Get historical OHLCV candles", "parameters": {"symbol": "string", "timeframe": "string", "limit": "int"}},
            {"name": "query_symbols", "description": "Get all available trading symbols", "parameters": {}},
        ]

    async def execute_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Execute a tool by name."""
        tools_map = {
            "query_balance": self.query_balance,
            "query_positions": self.query_positions,
            "query_quote": self.query_quote,
            "query_quotes": self.query_quotes,
            "query_ohlcv": self.query_ohlcv,
            "query_symbols": self.query_symbols,
        }
        tool = tools_map.get(tool_name)
        if not tool:
            return {"error": f"Unknown tool: {tool_name}"}
        return await tool(**kwargs)
