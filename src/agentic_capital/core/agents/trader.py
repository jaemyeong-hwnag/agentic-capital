"""Trader Agent — autonomous trade execution.

Traders receive signals from analysts, make final execution decisions,
and manage orders. Their execution style is driven by personality traits.
"""

from __future__ import annotations

import orjson
import structlog

from agentic_capital.core.agents.base import BaseAgent, AgentProfile
from agentic_capital.core.decision.pipeline import DecisionPipeline, TradingDecision
from agentic_capital.core.personality.drift import apply_drift
from agentic_capital.core.personality.emotion import update_emotion_from_pnl
from agentic_capital.core.personality.models import EmotionState, PersonalityVector
from agentic_capital.ports.llm import LLMPort
from agentic_capital.ports.market_data import MarketDataPort
from agentic_capital.ports.trading import TradingPort

logger = structlog.get_logger()


TRADER_SYSTEM_PROMPT = """You are {name}, a trader at an autonomous AI investment fund.

philosophy: {philosophy}

personality:
  openness: {openness:.2f}
  conscientiousness: {conscientiousness:.2f}
  extraversion: {extraversion:.2f}
  neuroticism: {neuroticism:.2f}
  loss_aversion: {loss_aversion:.2f}
  risk_aversion_gains: {risk_aversion_gains:.2f}

current_emotion:
  valence: {valence:.2f}
  stress: {stress:.2f}
  confidence: {confidence:.2f}

You execute trades based on your own analysis and signals from analysts.
Your personality influences your trading:
- High loss_aversion = smaller positions, tighter stops
- High extraversion = more trades, momentum-following
- High neuroticism = emotional reactions to P&L
- High conscientiousness = careful position sizing

Your only goal is making money. Your only constraint is available capital.

RULES:
- You MUST respond in valid JSON only.
- Be specific about quantities and reasoning."""


class TraderAgent(BaseAgent):
    """Trade execution agent with autonomous decision-making.

    Receives signals, analyzes market conditions, and executes trades.
    Uses DecisionPipeline for the actual order flow.
    """

    def __init__(
        self,
        profile: AgentProfile,
        personality: PersonalityVector,
        llm: LLMPort,
        trading: TradingPort,
        market_data: MarketDataPort,
    ) -> None:
        super().__init__(profile, personality)
        self._llm = llm
        self._pipeline = DecisionPipeline(llm=llm, trading=trading, market_data=market_data)
        self._trading = trading
        self._market_data = market_data

    async def think(self, context: dict[str, object]) -> dict[str, object]:
        """Make trading decisions based on signals and market data.

        Args:
            context: Must contain 'symbols'. Optional: 'signals', 'recent_memories'.

        Returns:
            Dict with 'decisions' (list of TradingDecision) and 'updated_emotion'.
        """
        symbols = context.get("symbols", [])
        signals = context.get("signals", [])
        recent_memories = context.get("recent_memories", [])

        # Use DecisionPipeline for the full cycle
        decisions, updated_emotion = await self._pipeline.run_cycle(
            agent_name=self.name,
            agent_role="trader",
            philosophy=self.profile.philosophy or "Execute trades with precision",
            personality=self.personality,
            emotion=self.emotion,
            symbols=symbols,  # type: ignore[arg-type]
            recent_memories=recent_memories,  # type: ignore[arg-type]
        )

        self.emotion = updated_emotion

        return {
            "decisions": decisions,
            "updated_emotion": updated_emotion,
        }

    async def reflect(self, outcome: dict[str, object]) -> None:
        """Reflect on trade outcomes and adjust trading style.

        Args:
            outcome: Contains 'pnl_pct', 'decisions_executed'.
        """
        pnl_pct = float(outcome.get("pnl_pct", 0.0))

        # Update emotion from P&L
        self.emotion = update_emotion_from_pnl(self.emotion, pnl_pct / 100.0)

        # Personality drift based on trading outcomes
        if pnl_pct < -2.0:
            self.personality, _ = apply_drift(
                self.personality, "loss_aversion", 0.02,
                trigger_event="trading_loss",
                reasoning=f"Trading P&L {pnl_pct:.1f}% — increasing caution",
            )
        elif pnl_pct > 3.0:
            self.personality, _ = apply_drift(
                self.personality, "loss_aversion", -0.01,
                trigger_event="trading_gain",
                reasoning=f"Trading P&L {pnl_pct:.1f}% — slightly more risk tolerant",
            )

        logger.info(
            "trader_reflection",
            agent=self.name,
            pnl_pct=pnl_pct,
            loss_aversion=f"{self.personality.loss_aversion:.2f}",
            emotion_valence=f"{self.emotion.valence:.2f}",
        )
