"""Simulation ORM models — simulation runs, company snapshots."""

import uuid
from datetime import datetime

from sqlalchemy import DECIMAL, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from agentic_capital.infra.models.base import Base


class SimulationRunModel(Base):
    """simulation_runs table — experiment metadata for reproducibility."""

    __tablename__ = "simulation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    llm_model: Mapped[str] = mapped_column(String(100), nullable=False)
    llm_version: Mapped[str] = mapped_column(String(50), default="")
    embedding_model: Mapped[str] = mapped_column(String(100), default="")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)  # Full hyperparameter snapshot
    initial_capital: Mapped[float] = mapped_column(DECIMAL(20, 4), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running, completed, aborted


class CompanySnapshotModel(Base):
    """company_snapshots — TimescaleDB hypertable for company-wide metrics."""

    __tablename__ = "company_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    simulation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    total_capital: Mapped[float] = mapped_column(DECIMAL(20, 4), nullable=False)
    allocated_capital: Mapped[float] = mapped_column(DECIMAL(20, 4), nullable=False)
    cash: Mapped[float] = mapped_column(DECIMAL(20, 4), nullable=False)
    agents_count: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_pnl_pct: Mapped[float] = mapped_column(Float, default=0)
    cumulative_pnl_pct: Mapped[float] = mapped_column(Float, default=0)
    sharpe_30d: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    org_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)  # Org state at this point
