"""Memory ORM models — A-MEM notes, episodic details."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from agentic_capital.infra.models.base import Base


class MemoryModel(Base):
    """memories table — A-MEM Zettelkasten notes with embeddings."""

    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    simulation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    memory_type: Mapped[str] = mapped_column(String(20), nullable=False)  # episodic, semantic, procedural

    # A-MEM fields
    context: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list] = mapped_column(JSONB, default=list)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    links: Mapped[list] = mapped_column(JSONB, default=list)  # Cross-references (UUID list)

    # REMEMBERER fields
    q_value: Mapped[float] = mapped_column(Float, default=0.5)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    access_count: Mapped[int] = mapped_column(Integer, default=0)

    # Embedding vector — stored as JSONB for pgvectorscale compatibility
    # In Phase 2, migrate to VECTOR(1024) column with HNSW index
    embedding: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    last_accessed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EpisodicDetailModel(Base):
    """episodic_details table — detailed experience records."""

    __tablename__ = "episodic_details"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_regime: Mapped[str] = mapped_column(String(50), default="")
    reflection: Mapped[str] = mapped_column(Text, default="")
