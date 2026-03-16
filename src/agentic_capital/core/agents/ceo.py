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
from agentic_capital.core.personality.models import EmotionState, PersonalityVector
from agentic_capital.ports.llm import LLMPort

logger = structlog.get_logger()


def _ceo_system_prompt(name: str, philosophy: str, personality, emotion) -> str:
    """Compact CEO system prompt. ~75% token reduction vs verbose format."""
    from agentic_capital.formats.compact import LEGEND, MANDATE
    p, e = personality, emotion
    p_str = (
        f"O:{p.openness:.2f} C:{p.conscientiousness:.2f} E:{p.extraversion:.2f} "
        f"A:{p.agreeableness:.2f} N:{p.neuroticism:.2f} LA:{p.loss_aversion:.2f}"
    )
    e_str = f"V:{e.valence:.2f} ST:{e.stress:.2f} CF:{e.confidence:.2f}"
    return (
        f"{LEGEND}\n"
        f"<agent name=\"{name}\" role=\"CEO\"><phi>{philosophy}</phi>\n"
        f"<P>{p_str}</P>\n<E>{e_str}</E></agent>\n"
        f"{MANDATE}\n"
        "act:hire|fire|promote|demote|reallocate|strategy|create_role|abolish_role|noop\n"
        "JSON:{actions:[{type,target,detail,reason,capital?}],strategy,cf}"
    )


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

        system = _ceo_system_prompt(
            name=self.name,
            philosophy=self.profile.philosophy or "Maximize returns through optimal organization",
            personality=self.personality,
            emotion=self.emotion,
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
        """Reflect on outcomes — AI decides how to process experience.

        No system-enforced personality drift. The agent autonomously
        decides what to feel and how to adapt based on raw data.
        """
        # Data is available — agent decides what to do with it
        logger.info(
            "ceo_reflection",
            outcome=outcome,
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
