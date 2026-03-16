"""Trade-related ORM models — trades, positions."""

import uuid
from datetime import datetime

from sqlalchemy import DECIMAL, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from agentic_capital.infra.models.base import Base


class TradeModel(Base):
    """trades table — every executed trade with full context."""

    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    simulation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(20), nullable=False)  # crypto, us_stock, kr_stock
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # buy, sell
    order_type: Mapped[str] = mapped_column(String(10), default="market")
    quantity: Mapped[float] = mapped_column(DECIMAL(20, 8), nullable=False)
    price: Mapped[float] = mapped_column(DECIMAL(20, 8), nullable=False)
    total_value: Mapped[float] = mapped_column(DECIMAL(20, 4), nullable=False)
    commission: Mapped[float] = mapped_column(DECIMAL(20, 4), default=0)  # estimated fee
    net_value: Mapped[float] = mapped_column(DECIMAL(20, 4), default=0)   # total_value ± commission
    thesis: Mapped[str] = mapped_column(Text, default="")  # Investment rationale
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    personality_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    emotion_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    memory_refs: Mapped[list] = mapped_column(JSONB, default=list)  # Referenced memory IDs
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    status: Mapped[str] = mapped_column(String(20), default="filled")  # filled, partial, rejected


class PositionModel(Base):
    """positions table — current open positions per agent."""

    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    simulation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    market: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[float] = mapped_column(DECIMAL(20, 8), nullable=False)
    avg_price: Mapped[float] = mapped_column(DECIMAL(20, 8), nullable=False)
    unrealized_pnl: Mapped[float] = mapped_column(DECIMAL(20, 4), default=0)
    unrealized_pnl_pct: Mapped[float] = mapped_column(Float, default=0)
    thesis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
