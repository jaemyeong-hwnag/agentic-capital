"""LangGraph nodes — autonomous agent actions.

Each node is a tool that agents CAN use. The agent (via LLM) decides
which nodes to invoke, in what order, with what parameters.
System only records results — no enforcement of behavior.
"""

from __future__ import annotations

import structlog

from agentic_capital.core.agents.base import BaseAgent
from agentic_capital.core.agents.ceo import CEOAgent
from agentic_capital.core.agents.analyst import AnalystAgent
from agentic_capital.core.agents.trader import TraderAgent
from agentic_capital.core.decision.reflection import reflect_on_trades
from agentic_capital.core.decision.pipeline import TradingDecision
from agentic_capital.core.personality.emotion import update_emotion_from_pnl
from agentic_capital.graph.state import AgentWorkflowState

logger = structlog.get_logger()


async def gather_data(state: AgentWorkflowState, agent: BaseAgent, **deps) -> AgentWorkflowState:
    """Gather market data, balance, positions — agent decides what to look at.

    This node makes data AVAILABLE. The agent's LLM decides
    what to actually use in its decision-making.
    """
    trading = deps.get("trading")
    market_data_adapter = deps.get("market_data")
    symbols = deps.get("symbols", [])

    updates: AgentWorkflowState = {}  # type: ignore[typeddict-item]

    try:
        if trading:
            balance = await trading.get_balance()
            positions = await trading.get_positions()
            updates["balance"] = {"total": balance.total, "available": balance.available, "currency": balance.currency}
            updates["positions"] = [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_price": p.avg_price,
                    "current_price": p.current_price,
                    "unrealized_pnl_pct": p.unrealized_pnl_pct,
                }
                for p in positions
            ]

        if market_data_adapter and symbols:
            mkt = []
            for symbol in symbols:
                try:
                    quote = await market_data_adapter.get_quote(symbol)
                    mkt.append({"symbol": symbol, "price": quote.price, "volume": quote.volume or 0})
                except Exception:
                    logger.warning("quote_fetch_failed", symbol=symbol)
            updates["market_data"] = mkt

    except Exception as e:
        updates["errors"] = [f"gather_data: {e}"]
        logger.exception("gather_data_failed", agent=state.get("agent_name"))

    return updates


async def think(state: AgentWorkflowState, agent: BaseAgent, **deps) -> AgentWorkflowState:
    """Agent thinks and makes decisions — fully autonomous.

    The agent uses its personality, emotion, and whatever data it has
    gathered to make decisions. No restrictions on what it can decide.
    """
    updates: AgentWorkflowState = {}  # type: ignore[typeddict-item]

    try:
        context = {
            "market_data": state.get("market_data", []),
            "portfolio": state.get("balance", {}),
            "positions": state.get("positions", []),
            "working_memory": [],
            "symbols": deps.get("symbols", []),
            "agents": state.get("agent_roster", []),
            "company_state": state.get("company_state", {}),
            "recent_performance": [],
            "signals": state.get("messages_received", []),
            "recent_memories": [],
        }

        result = await agent.think(context)

        # Normalize decisions to dicts for state storage
        decisions = result.get("decisions", result.get("actions", result.get("signals", [])))
        decision_dicts = []
        for d in decisions:
            if isinstance(d, dict):
                decision_dicts.append(d)
            elif hasattr(d, "__dict__"):
                decision_dicts.append(vars(d))
            else:
                decision_dicts.append({"value": str(d)})

        updates["decisions"] = decision_dicts

        # Messages to send (analyst signals, CEO announcements, etc.)
        if "signals" in result:
            messages = []
            for s in result["signals"]:
                if hasattr(s, "symbol"):
                    messages.append({
                        "type": "SIGNAL",
                        "symbol": s.symbol,
                        "signal": s.signal,
                        "confidence": s.confidence,
                        "thesis": s.thesis,
                    })
            updates["messages_to_send"] = messages

    except Exception as e:
        updates["errors"] = state.get("errors", []) + [f"think: {e}"]
        updates["decisions"] = []
        logger.exception("think_failed", agent=state.get("agent_name"))

    return updates


async def reflect(state: AgentWorkflowState, agent: BaseAgent, **deps) -> AgentWorkflowState:
    """Agent reflects on outcomes — personality drift, emotion update.

    Reflection is autonomous — the agent processes its own
    experience and adjusts internally. System only records the changes.
    """
    updates: AgentWorkflowState = {}  # type: ignore[typeddict-item]

    try:
        # Calculate P&L from positions
        positions = state.get("positions", [])
        total_pnl_pct = 0.0
        if positions:
            total_pnl_pct = sum(p.get("unrealized_pnl_pct", 0) for p in positions) / len(positions)

        # Agent reflects
        await agent.reflect({"pnl_pct": total_pnl_pct})

        # Record updated emotion
        updates["emotion"] = {
            "valence": agent.emotion.valence,
            "arousal": agent.emotion.arousal,
            "dominance": agent.emotion.dominance,
            "stress": agent.emotion.stress,
            "confidence": agent.emotion.confidence,
        }

        # Record any personality changes
        updates["reflection"] = f"P&L: {total_pnl_pct:.2f}%"

    except Exception as e:
        updates["errors"] = state.get("errors", []) + [f"reflect: {e}"]
        logger.exception("reflect_failed", agent=state.get("agent_name"))

    return updates


async def record(state: AgentWorkflowState, agent: BaseAgent, **deps) -> AgentWorkflowState:
    """Record everything to DB — system's only job is to record.

    All actions, decisions, emotions, personality changes are persisted.
    This is the "논문급 기록" requirement.
    """
    recorder = deps.get("recorder")
    if not recorder:
        return {}  # type: ignore[return-value]

    try:
        from uuid import UUID

        agent_id = UUID(state["agent_id"]) if isinstance(state.get("agent_id"), str) else agent.agent_id

        # Record emotion state
        await recorder.record_emotion(
            agent_id=agent_id,
            emotion=agent.emotion,
            trigger=f"cycle_{state.get('cycle_number', 0)}",
        )

        # Record decisions
        for d in state.get("decisions", []):
            if isinstance(d, dict) and "action" in d:
                decision = TradingDecision(
                    action=d.get("action", "HOLD"),
                    symbol=d.get("symbol", ""),
                    quantity=int(d.get("quantity", 0)),
                    reason=d.get("reason", ""),
                    confidence=float(d.get("confidence", 0.5)),
                )
                await recorder.record_decision(
                    agent_id=agent_id,
                    decision=decision,
                    personality=agent.personality,
                    emotion=agent.emotion,
                    status="executed",
                )

        await recorder.commit()

    except Exception as e:
        logger.exception("record_failed", agent=state.get("agent_name"), error=str(e))

    return {}  # type: ignore[return-value]
