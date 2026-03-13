"""Market data port — abstract interface for price/OHLCV data."""

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class OHLCV(BaseModel):
    """Single OHLCV candle."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class Quote(BaseModel):
    """Current price quote."""

    symbol: str
    price: float
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    timestamp: datetime | None = None


class MarketDataPort(ABC):
    """Abstract interface for market data retrieval.

    Adapters implement this for each data source.
    """

    @abstractmethod
    async def get_quote(self, symbol: str) -> Quote:
        """Get current price quote for a symbol."""

    @abstractmethod
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        limit: int = 100,
    ) -> list[OHLCV]:
        """Get historical OHLCV data."""

    @abstractmethod
    async def get_symbols(self) -> list[str]:
        """Get available symbols."""
