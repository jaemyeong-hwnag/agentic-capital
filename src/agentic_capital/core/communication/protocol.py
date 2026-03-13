"""LACP protocol — structured agent communication messages."""

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MessageType(StrEnum):
    PLAN = "PLAN"
    ACT = "ACT"
    OBSERVE = "OBSERVE"
    SIGNAL = "SIGNAL"


class AgentMessage(BaseModel):
    """LACP protocol message between agents."""

    id: UUID = Field(default_factory=uuid4)
    type: MessageType
    sender_id: UUID
    receiver_id: UUID | None = None  # None = broadcast
    priority: float = Field(default=0.5, ge=0.0, le=1.0)
    content: dict[str, object] = Field(default_factory=dict)
    memory_refs: list[UUID] = Field(default_factory=list)
    ttl: int = 3  # Valid for N rounds
