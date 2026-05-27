"""Agent-related ORM models — agents, personality, emotion history."""

import uuid
from datetime import datetime

from sqlalchemy import DECIMAL, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from agentic_capital.infra.models.base import Base


class AgentModel(Base):
    """agents table — core agent identity."""

    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    simulation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, fired, retired
    philosophy: Mapped[str] = mapped_column(Text, default="")
    allocated_capital: Mapped[float] = mapped_column(DECIMAL(20, 4), default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)


class AgentPersonalityModel(Base):
    """agent_personality table — current 15D personality vector."""

    __tablename__ = "agent_personality"

    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    # Big5 (OCEAN)
    openness: Mapped[float] = mapped_column(Float, default=0.5)
    conscientiousness: Mapped[float] = mapped_column(Float, default=0.5)
    extraversion: Mapped[float] = mapped_column(Float, default=0.5)
    agreeableness: Mapped[float] = mapped_column(Float, default=0.5)
    neuroticism: Mapped[float] = mapped_column(Float, default=0.5)
    # HEXACO
    honesty_humility: Mapped[float] = mapped_column(Float, default=0.5)
    # Prospect Theory
    loss_aversion: Mapped[float] = mapped_column(Float, default=0.5)
    risk_aversion_gains: Mapped[float] = mapped_column(Float, default=0.5)
    risk_aversion_losses: Mapped[float] = mapped_column(Float, default=0.5)
    probability_weighting: Mapped[float] = mapped_column(Float, default=0.5)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)


class AgentPersonalityHistoryModel(Base):
    """agent_personality_history — TimescaleDB hypertable for personality drift."""

    __tablename__ = "agent_personality_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    parameter: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[float] = mapped_column(Float, nullable=False)
    new_value: Mapped[float] = mapped_column(Float, nullable=False)
    trigger_event: Mapped[str] = mapped_column(String(100), nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, default="")


class AgentEmotionHistoryModel(Base):
    """agent_emotion_history — TimescaleDB hypertable for emotion snapshots."""

    __tablename__ = "agent_emotion_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    valence: Mapped[float] = mapped_column(Float, nullable=False)
    arousal: Mapped[float] = mapped_column(Float, nullable=False)
    dominance: Mapped[float] = mapped_column(Float, nullable=False)
    stress: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    trigger: Mapped[str] = mapped_column(String(100), default="")


class AgentDecisionModel(Base):
    """agent_decisions — every AI decision with full context snapshot."""

    __tablename__ = "agent_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    simulation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    decision_type: Mapped[str] = mapped_column(String(50), nullable=False)  # trade, hr, strategy
    action: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    personality_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    emotion_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    context_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    outcome: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)


class RawModelFailureModel(Base):
    """raw_model_failures — structured local model failure evidence.

    AgentDecisionModel keeps the decision-audit surface. This table gives ops,
    regression, and retraining jobs a stable failure feed without parsing
    human-facing decision rows.
    """

    __tablename__ = "raw_model_failures"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    simulation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    cycle_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_type: Mapped[str] = mapped_column(String(100), nullable=False)
    first_failing_stage: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    sidecar_latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_ids: Mapped[list] = mapped_column(JSONB, default=list)
    risk_flags: Mapped[list] = mapped_column(JSONB, default=list)
    sidecar_stage_metrics: Mapped[list] = mapped_column(JSONB, default=list)
    failure_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    failure_body_summary: Mapped[str] = mapped_column(Text, default="")
    retrain_candidate: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
