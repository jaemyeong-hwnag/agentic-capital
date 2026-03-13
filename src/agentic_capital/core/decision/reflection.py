"""Reflection system — learn from outcomes, trigger personality drift."""

from __future__ import annotations

import structlog

from agentic_capital.core.decision.pipeline import TradingDecision
from agentic_capital.core.personality.drift import apply_drift
from agentic_capital.core.personality.models import PersonalityVector

logger = structlog.get_logger()


def reflect_on_trades(
    personality: PersonalityVector,
    decisions: list[TradingDecision],
    pnl_pct: float,
) -> tuple[PersonalityVector, list[dict]]:
    """Reflect on trading outcomes and apply personality drift.

    Args:
        personality: Current personality vector.
        decisions: Decisions made this cycle.
        pnl_pct: Overall P&L percentage for this cycle.

    Returns:
        Updated personality and list of drift events.
    """
    if not decisions:
        return personality, []

    drift_events = []
    updated = personality

    # Significant loss → increase loss_aversion, increase conscientiousness
    if pnl_pct < -2.0:
        updated, event = apply_drift(
            updated, "loss_aversion", 0.02,
            trigger_event="significant_loss",
            reasoning=f"P&L {pnl_pct:.1f}% triggered increased loss aversion",
        )
        drift_events.append(event.model_dump())

        updated, event = apply_drift(
            updated, "conscientiousness", 0.01,
            trigger_event="significant_loss",
            reasoning="Loss encourages more careful analysis",
        )
        drift_events.append(event.model_dump())
        logger.info("reflection_loss_drift", pnl_pct=pnl_pct, drifts=len(drift_events))

    # Significant gain → slight decrease in loss_aversion, increase confidence-related traits
    elif pnl_pct > 3.0:
        updated, event = apply_drift(
            updated, "loss_aversion", -0.01,
            trigger_event="significant_gain",
            reasoning=f"P&L {pnl_pct:.1f}% slightly reduced loss aversion",
        )
        drift_events.append(event.model_dump())

        updated, event = apply_drift(
            updated, "openness", 0.01,
            trigger_event="significant_gain",
            reasoning="Success encourages exploring new strategies",
        )
        drift_events.append(event.model_dump())
        logger.info("reflection_gain_drift", pnl_pct=pnl_pct, drifts=len(drift_events))

    return updated, drift_events
