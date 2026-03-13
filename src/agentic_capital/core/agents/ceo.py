"""CEO Agent — autonomous organizational management.

The CEO has full autonomy over:
- Hiring/firing agents
- Role creation/abolishment
- Capital allocation
- Strategy direction
- Organizational structure

Only constraint: available capital.
"""

from __future__ import annotations

import orjson
import structlog

from agentic_capital.core.agents.base import AgentContext, AgentProfile, BaseAgent
from agentic_capital.core.decision.prompts import build_ceo_prompt
from agentic_capital.core.organization.hr import HREvent, HREventType
from agentic_capital.core.organization.roles import Role
from agentic_capital.core.personality.drift import apply_drift
from agentic_capital.core.personality.models import EmotionState, PersonalityVector
from agentic_capital.ports.llm import LLMPort

logger = structlog.get_logger()


CEO_SYSTEM_PROMPT = """You are {name}, the CEO of an autonomous AI investment fund.

philosophy: {philosophy}

personality:
  openness: {openness:.2f}
  conscientiousness: {conscientiousness:.2f}
  extraversion: {extraversion:.2f}
  agreeableness: {agreeableness:.2f}
  neuroticism: {neuroticism:.2f}
  loss_aversion: {loss_aversion:.2f}

current_emotion:
  valence: {valence:.2f}
  stress: {stress:.2f}
  confidence: {confidence:.2f}

You have FULL AUTONOMY over the organization. You can do anything:
- Hire agents, fire agents, promote, demote
- Create/abolish/rename roles
- Reallocate capital between agents
- Set or change strategy direction
- Restructure the entire organization
- Or do nothing if you judge that's best

Your only goal is making money. Your only constraint is available capital.
All decisions are yours — no restrictions on what you can do or how.
Your personality deeply influences your management style.

RULES:
- You MUST respond in valid JSON only."""


class CEOAction:
    """A single organizational action decided by the CEO."""

    def __init__(
        self,
        action_type: str,
        target: str = "",
        detail: str = "",
        reason: str = "",
        capital: float = 0.0,
        personality_spec: dict | None = None,
    ) -> None:
        self.action_type = action_type  # hire, fire, reallocate, strategy, create_role
        self.target = target
        self.detail = detail
        self.reason = reason
        self.capital = capital
        self.personality_spec = personality_spec or {}


class CEOAgent(BaseAgent):
    """CEO agent with full organizational autonomy.

    The CEO evaluates company performance and makes strategic decisions
    about hiring, firing, capital allocation, and organizational structure.
    All decisions are influenced by personality and emotion state.
    """

    def __init__(
        self,
        profile: AgentProfile,
        personality: PersonalityVector,
        llm: LLMPort,
    ) -> None:
        super().__init__(profile, personality)
        self._llm = llm

    async def think(self, context: dict[str, object]) -> dict[str, object]:
        """Evaluate organization and make strategic decisions.

        Args:
            context: Must contain 'agents', 'company_state', 'recent_performance'.

        Returns:
            Dict with 'actions' (list of CEOAction) and 'strategy_update'.
        """
        agents = context.get("agents", [])
        company_state = context.get("company_state", {})
        recent_performance = context.get("recent_performance", [])

        system = CEO_SYSTEM_PROMPT.format(
            name=self.name,
            philosophy=self.profile.philosophy or "Maximize returns through optimal organization",
            openness=self.personality.openness,
            conscientiousness=self.personality.conscientiousness,
            extraversion=self.personality.extraversion,
            agreeableness=self.personality.agreeableness,
            neuroticism=self.personality.neuroticism,
            loss_aversion=self.personality.loss_aversion,
            valence=self.emotion.valence,
            stress=self.emotion.stress,
            confidence=self.emotion.confidence,
        )

        prompt = build_ceo_prompt(
            agents=agents,  # type: ignore[arg-type]
            company_state=company_state,  # type: ignore[arg-type]
            recent_performance=recent_performance,  # type: ignore[arg-type]
        )

        actions = await self._get_ceo_decisions(system, prompt)

        return {
            "actions": actions,
            "strategy_update": actions[-1].detail if actions else "",
        }

    async def reflect(self, outcome: dict[str, object]) -> None:
        """Reflect on organizational decisions and their outcomes.

        Args:
            outcome: Contains 'pnl_pct', 'agents_performance', etc.
        """
        pnl_pct = float(outcome.get("pnl_pct", 0.0))

        # CEO personality drifts based on company performance
        if pnl_pct < -3.0:
            # Poor performance → more cautious, higher conscientiousness
            self.personality, _ = apply_drift(
                self.personality, "conscientiousness", 0.02,
                trigger_event="company_loss",
                reasoning=f"Company P&L {pnl_pct:.1f}% — being more careful",
            )
            self.personality, _ = apply_drift(
                self.personality, "neuroticism", 0.01,
                trigger_event="company_loss",
                reasoning="Company losses increase stress sensitivity",
            )
        elif pnl_pct > 5.0:
            # Good performance → more confident, open to expansion
            self.personality, _ = apply_drift(
                self.personality, "openness", 0.01,
                trigger_event="company_gain",
                reasoning=f"Company P&L {pnl_pct:.1f}% — open to expansion",
            )
            self.personality, _ = apply_drift(
                self.personality, "extraversion", 0.01,
                trigger_event="company_gain",
                reasoning="Success encourages bolder moves",
            )

        logger.info(
            "ceo_reflection",
            pnl_pct=pnl_pct,
            conscientiousness=f"{self.personality.conscientiousness:.2f}",
            openness=f"{self.personality.openness:.2f}",
        )

    async def _get_ceo_decisions(self, system: str, prompt: str) -> list[CEOAction]:
        """Parse CEO decisions from LLM response."""
        try:
            response = await self._llm.generate(prompt, system=system)

            json_str = response.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            parsed = orjson.loads(json_str)
            actions = []
            for a in parsed.get("actions", []):
                action_type = a.get("type", "strategy")
                actions.append(CEOAction(
                    action_type=action_type,
                    target=a.get("target", ""),
                    detail=a.get("detail", ""),
                    reason=a.get("reason", ""),
                    capital=float(a.get("capital", 0)),
                    personality_spec=a.get("personality", {}),
                ))

            logger.info("ceo_decisions_parsed", count=len(actions))
            return actions
        except Exception:
            logger.exception("ceo_decision_failed")
            return []

    def action_to_hr_event(self, action: CEOAction, target_agent_id: object) -> HREvent | None:
        """Convert a CEO action to an HR event for recording."""
        from uuid import UUID

        if not isinstance(target_agent_id, UUID):
            return None

        event_map = {
            "hire": HREventType.HIRE,
            "fire": HREventType.FIRE,
            "promote": HREventType.PROMOTE,
            "demote": HREventType.DEMOTE,
            "reallocate": HREventType.REWARD,
        }

        event_type = event_map.get(action.action_type)
        if event_type is None:
            return None

        return HREvent(
            event_type=event_type,
            target_agent_id=target_agent_id,
            decided_by=self.agent_id,
            reasoning=action.reason,
            new_capital=action.capital if action.capital > 0 else None,
        )
