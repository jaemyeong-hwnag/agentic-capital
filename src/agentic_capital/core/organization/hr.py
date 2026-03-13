"""HR system — hiring, firing, promotion, demotion (fully autonomous)."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class HREventType(StrEnum):
    HIRE = "hire"
    FIRE = "fire"
    PROMOTE = "promote"
    DEMOTE = "demote"
    ROLE_CHANGE = "role_change"
    REWARD = "reward"
    WARN = "warn"


class HREvent(BaseModel):
    """Record of an HR decision."""

    event_type: HREventType
    target_agent_id: UUID
    decided_by: UUID
    old_role_id: UUID | None = None
    new_role_id: UUID | None = None
    old_capital: float | None = None
    new_capital: float | None = None
    reasoning: str = ""
    context_snapshot: dict[str, object] = Field(default_factory=dict)
