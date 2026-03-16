"""LACP protocol — compact AI-to-AI message schema.

Wire format (tool layer): TYPE|FROM|TO|TS|k:v,k:v
Types: SIG=signal  INSTR=instruction  RPT=report  QRY=query  ACK=ack  ERR=error
Bus format (Redis/MessagePack): AgentMessage binary blob
"""

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MessageType(StrEnum):
    # Compact aliases (tool-layer wire format)
    SIG = "SIG"      # trading signal
    INSTR = "INSTR"  # instruction / command
    RPT = "RPT"      # status report
    QRY = "QRY"      # query / request
    ACK = "ACK"      # acknowledgement / response
    ERR = "ERR"      # error
    # Legacy full names (backward compat)
    PLAN = "PLAN"
    ACT = "ACT"
    OBSERVE = "OBSERVE"
    SIGNAL = "SIGNAL"


class AgentMessage(BaseModel):
    """LACP protocol message — compact binary bus format."""

    id: UUID = Field(default_factory=uuid4)
    type: MessageType
    sender_id: UUID
    receiver_id: UUID | None = None  # None = broadcast
    priority: float = Field(default=0.5, ge=0.0, le=1.0)
    content: str | dict[str, object] = Field(default_factory=dict)  # str=compact, dict=legacy
    memory_refs: list[UUID] = Field(default_factory=list)
    ttl: int = 3  # Valid for N rounds
