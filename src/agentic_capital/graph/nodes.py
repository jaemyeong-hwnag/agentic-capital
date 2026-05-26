"""Recording node — transparent DB persistence after agent cycles.

This is the only system-enforced action: recording what happened.
Agents don't control this — it happens automatically after every cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from agentic_capital.core.agents.base import BaseAgent

logger = structlog.get_logger()

PSYCHOLOGY_DECISION_TYPES = {"psychology", "psychology_context", "psychology_evaluation"}
FINANCE_RECORD_DECISION_TYPES = {"finance_paper_shadow_decision", "raw_model_failure"}


async def record_cycle(
    agent: BaseAgent,
    cycle_number: int,
    *,
    decisions: list[dict],
    messages: list[dict],
    recorder: object | None = None,
) -> None:
    """Record all decisions, emotions, messages, and positions to DB.

    Called automatically after every agent cycle. Agents have no control
    over what gets recorded — everything is persisted for full auditability.
    """
    if not recorder:
        return

    try:
        from uuid import UUID

        agent_id = agent.agent_id

        # Record emotion state
        await recorder.record_emotion(
            agent_id=agent_id,
            emotion=agent.emotion,
            trigger=f"cycle_{cycle_number}",
        )

        # Record all decisions
        for d in decisions:
            if not isinstance(d, dict):
                continue

            decision_type = d.get("type", d.get("decision_type", "general"))

            if str(decision_type) in PSYCHOLOGY_DECISION_TYPES:
                if hasattr(recorder, "record_psychology_context"):
                    await recorder.record_psychology_context(
                        agent_id=agent_id,
                        psychology_context=d.get("psychology_context", d),
                        source=str(d.get("source") or "psychology_model_suite"),
                        cycle_number=cycle_number,
                    )
                continue

            if str(decision_type) in FINANCE_RECORD_DECISION_TYPES:
                await recorder.record_decision(
                    agent_id=agent_id,
                    personality=agent.personality,
                    emotion=agent.emotion,
                    decision_type=str(decision_type),
                    action=d.get("action", "WAIT"),
                    reasoning=d.get("reason", d.get("failure_type", "")),
                    confidence=float(d.get("confidence", 0.5)),
                    context_snapshot=d,
                    outcome={
                        "record_type": decision_type,
                        "paper_trade_only": True,
                        "would_submit_order": False,
                    },
                )
                continue

            if decision_type in ("trade", "BUY", "SELL", "HOLD", "buy", "sell", "hold") or (
                d.get("action") in ("BUY", "SELL", "buy", "sell") and d.get("symbol")
            ):
                from agentic_capital.core.decision.pipeline import TradingDecision
                try:
                    trade_reason = d.get("reason", "")
                    decision = TradingDecision(
                        action=d.get("action", d.get("type", "HOLD")),
                        symbol=d.get("symbol", ""),
                        quantity=int(d.get("quantity", 0)),
                        reason=trade_reason,
                        confidence=float(d.get("confidence", 0.5)),
                    )
                    commission = float(d.get("commission") or 0.0)
                    await recorder.record_decision(
                        agent_id=agent_id,
                        decision=decision,
                        personality=agent.personality,
                        emotion=agent.emotion,
                        status=d.get("status", "executed"),
                        price=float(d.get("price") or 0.0),
                        market=d.get("market", "kr_stock"),
                        outcome={
                            "commission": commission,
                            "pnl_impact": -commission,
                            "order_id": d.get("order_id", ""),
                            "reason": trade_reason,
                        },
                    )
                except Exception:
                    logger.warning("trade_decision_record_failed", decision=d)

            elif decision_type in ("hire", "fire", "promote", "demote", "role_change", "reward", "warn"):
                await recorder.record_decision(
                    agent_id=agent_id,
                    personality=agent.personality,
                    emotion=agent.emotion,
                    decision_type="hr",
                    action=f"{decision_type} {d.get('target', '')}",
                    reasoning=d.get("reason", d.get("detail", "")),
                    confidence=float(d.get("confidence", 0.5)),
                    context_snapshot=d,
                    outcome={"type": decision_type},
                )
                # HR event
                target = d.get("target", "")
                try:
                    from agentic_capital.core.organization.hr import HREvent, HREventType
                    target_uuid = UUID(str(target)) if target else None
                    if target_uuid:
                        await recorder.record_hr_event(HREvent(
                            event_type=HREventType(decision_type),
                            target_agent_id=target_uuid,
                            decided_by=agent_id,
                            reasoning=d.get("reason", ""),
                            new_capital=float(d.get("capital", 0)) if d.get("capital") else None,
                        ))
                except (ValueError, KeyError):
                    pass

            else:
                await recorder.record_decision(
                    agent_id=agent_id,
                    personality=agent.personality,
                    emotion=agent.emotion,
                    decision_type=decision_type or "general",
                    action=d.get("action", d.get("detail", str(d))),
                    reasoning=d.get("reason", ""),
                    confidence=float(d.get("confidence", 0.5)),
                    context_snapshot=d,
                )

        # Record outbound messages
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            try:
                from agentic_capital.core.communication.protocol import AgentMessage, MessageType
                agent_msg = AgentMessage(
                    type=MessageType(msg.get("type", "SIGNAL")),
                    sender_id=agent_id,
                    receiver_id=None,
                    priority=float(msg.get("priority", 0.5)),
                    content=msg.get("content", msg),
                )
                await recorder.record_agent_message(agent_msg)
            except (ValueError, KeyError):
                logger.warning("message_record_skipped", msg=msg)

        await recorder.commit()

    except Exception:
        logger.exception("record_cycle_failed", agent=agent.name, cycle=cycle_number)
