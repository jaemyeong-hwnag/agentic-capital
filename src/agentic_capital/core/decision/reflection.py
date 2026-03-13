"""Reflection system — agents autonomously learn from outcomes.

No system-enforced personality drift. AI agents decide their own
responses to outcomes. Data is available — agents decide what to do with it.
"""

from __future__ import annotations

import structlog

from agentic_capital.core.decision.pipeline import TradingDecision
from agentic_capital.core.personality.models import PersonalityVector

logger = structlog.get_logger()


def reflect_on_trades(
    personality: PersonalityVector,
    decisions: list[TradingDecision],
    pnl_pct: float,
) -> tuple[PersonalityVector, list[dict]]:
    """Record trading outcomes for reflection — no system-enforced drift.

    The personality is returned unchanged. Drift decisions are made
    autonomously by the agent through its LLM, not by hardcoded rules.

    Args:
        personality: Current personality vector (returned unchanged).
        decisions: Decisions made this cycle.
        pnl_pct: Overall P&L percentage for this cycle.

    Returns:
        Unchanged personality and empty drift events list.
    """
    if not decisions:
        return personality, []

    logger.info(
        "reflection_recorded",
        decision_count=len(decisions),
        pnl_pct=pnl_pct,
    )

    # No system-enforced drift — agent decides autonomously
    return personality, []
