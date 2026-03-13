"""Market data ORM models — OHLCV time-series."""

import uuid
from datetime import datetime

from sqlalchemy import DECIMAL, DateTime, Float, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from agentic_capital.infra.models.base import Base


class MarketOHLCVModel(Base):
    """market_ohlcv — TimescaleDB hypertable for market candle data.

    Stores both absolute values (for order execution) and
    percentage changes (for AI consumption — StockTime format).
    """

    __tablename__ = "market_ohlcv"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(20), nullable=False)  # crypto, us_stock, kr_stock

    # Absolute values (for order execution)
    open: Mapped[float] = mapped_column(DECIMAL(20, 8), nullable=False)
    high: Mapped[float] = mapped_column(DECIMAL(20, 8), nullable=False)
    low: Mapped[float] = mapped_column(DECIMAL(20, 8), nullable=False)
    close: Mapped[float] = mapped_column(DECIMAL(20, 8), nullable=False)
    volume: Mapped[float] = mapped_column(DECIMAL(20, 4), nullable=False)

    # Percentage changes (for AI consumption — StockTime + NumeroLogic)
    open_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    low_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    close_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    vol_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
