"""Base agent abstract class — all agents inherit from this."""

from abc import ABC, abstractmethod
from uuid import UUID

from pydantic import BaseModel, Field

from agentic_capital.core.personality.models import EmotionState, PersonalityVector


class AgentProfile(BaseModel):
    """Immutable snapshot of an agent's identity."""

    id: UUID
    name: str
    role_id: UUID | None = None
    philosophy: str = ""
    allocated_capital: float = 0.0


class BaseAgent(ABC):
    """Abstract base for all autonomous agents.

    Every agent has a personality, emotion state, and can make decisions.
    The concrete behavior is determined by the agent's role and personality.
    """

    def __init__(self, profile: AgentProfile, personality: PersonalityVector) -> None:
        self.profile = profile
        self.personality = personality
        self.emotion = EmotionState()

    @abstractmethod
    async def think(self, context: dict[str, object]) -> dict[str, object]:
        """Process context and produce a decision.

        Args:
            context: Current market data, memory, org state.

        Returns:
            Decision dict with action, reasoning, confidence.
        """

    @abstractmethod
    async def reflect(self, outcome: dict[str, object]) -> None:
        """Reflect on the outcome of a decision and update internal state.

        Args:
            outcome: Result of the executed action.
        """

    @property
    def agent_id(self) -> UUID:
        return self.profile.id

    @property
    def name(self) -> str:
        return self.profile.name


class AgentContext(BaseModel):
    """Context assembled for an agent's decision-making."""

    market_data: dict[str, object] = Field(default_factory=dict)
    portfolio: dict[str, object] = Field(default_factory=dict)
    working_memory: list[dict[str, object]] = Field(default_factory=list)
    episodic_memory: list[dict[str, object]] = Field(default_factory=list)
    messages: list[dict[str, object]] = Field(default_factory=list)
    org_state: dict[str, object] = Field(default_factory=dict)
