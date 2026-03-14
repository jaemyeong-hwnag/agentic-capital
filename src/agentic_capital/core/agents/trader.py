"""Trader Agent — autonomous trade execution.

Traders execute trades using any method they choose.
No methodology constraints — complete autonomy within available capital.
"""

from __future__ import annotations

import structlog

from agentic_capital.core.agents.base import BaseAgent, AgentProfile
from agentic_capital.core.personality.models import PersonalityVector
from agentic_capital.ports.llm import LLMPort
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

Your only goal is making money. Your only constraint is available capital.
Use any trading method, approach, or philosophy you choose — zero restrictions.
Rational, irrational, intuitive, systematic, contrarian — all valid."""


class TraderAgent(BaseAgent):
    """Trade execution agent with complete autonomy.

    No methodology constraints. Executes trades via KIS using any approach.
    Main execution runs through the ReAct tool-use loop in workflow.py.
    """

    def __init__(
        self,
        profile: AgentProfile,
        personality: PersonalityVector,
        llm: LLMPort,
        trading: TradingPort,
    ) -> None:
        super().__init__(profile, personality)
        self._llm = llm
        self._trading = trading

    async def think(self, context: dict[str, object]) -> dict[str, object]:
        """Autonomous trading decisions — no forced methodology.

        Main execution happens via ReAct loop in workflow.py.
        """
        return {"decisions": [], "updated_emotion": self.emotion}

    async def reflect(self, outcome: dict[str, object]) -> None:
        """Reflect on outcomes — agent decides autonomously how to adapt."""
        logger.info(
            "trader_reflection",
            agent=self.name,
            outcome=outcome,
            loss_aversion=f"{self.personality.loss_aversion:.2f}",
            emotion_valence=f"{self.emotion.valence:.2f}",
        )
