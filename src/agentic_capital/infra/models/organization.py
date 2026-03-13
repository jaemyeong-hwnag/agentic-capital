"""Organization ORM models — roles, permissions, HR events, messages."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from agentic_capital.infra.models.base import Base


class RoleModel(Base):
    """roles table — dynamically created by CEO."""

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    simulation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    permissions: Mapped[list] = mapped_column(JSONB, default=list)
    report_to: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)


class PermissionHistoryModel(Base):
    """permission_history — TimescaleDB hypertable for permission changes."""

    __tablename__ = "permission_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # grant, revoke, modify
    changes: Mapped[dict] = mapped_column(JSONB, nullable=False)
    decided_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, default="")


class HREventModel(Base):
    """hr_events table — hiring, firing, promotion, etc."""

    __tablename__ = "hr_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    simulation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)  # hire, fire, promote, demote
    target_agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    decided_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    old_role_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    new_role_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    old_capital: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_capital: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    context_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)


class AgentMessageModel(Base):
    """agent_messages table — LACP protocol messages."""

    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    simulation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # PLAN, ACT, OBSERVE, SIGNAL
    sender_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    receiver_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    priority: Mapped[float] = mapped_column(Float, default=0.5)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    memory_refs: Mapped[list] = mapped_column(JSONB, default=list)
    ttl: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
