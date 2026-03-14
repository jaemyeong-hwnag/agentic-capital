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


def _trader_system_prompt(name: str, philosophy: str, personality, emotion) -> str:
    """Compact trader system prompt. ~75% token reduction vs verbose format."""
    from agentic_capital.formats.compact import LEGEND, MANDATE
    p, e = personality, emotion
    p_str = (
        f"O:{p.openness:.2f} C:{p.conscientiousness:.2f} E:{p.extraversion:.2f} "
        f"N:{p.neuroticism:.2f} LA:{p.loss_aversion:.2f} RAG:{p.risk_aversion_gains:.2f}"
    )
    e_str = f"V:{e.valence:.2f} ST:{e.stress:.2f} CF:{e.confidence:.2f}"
    return (
        f"{LEGEND}\n"
        f"<agent name=\"{name}\" role=\"trader\"><phi>{philosophy}</phi>\n"
        f"<P>{p_str}</P>\n<E>{e_str}</E></agent>\n"
        f"{MANDATE}"
    )


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
