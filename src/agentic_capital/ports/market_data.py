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
    market: str = "kr_stock"
    exchange: str | None = None         # Exchange code for overseas (e.g., "NASD")
    currency: str = "KRW"


class OrderBookLevel(BaseModel):
    """Single level in an order book."""

    price: float
    quantity: float


class OrderBook(BaseModel):
    """Order book (호가창)."""

    symbol: str
    bids: list[OrderBookLevel]          # Buy side (매수 호가), best bid first
    asks: list[OrderBookLevel]          # Sell side (매도 호가), best ask first
    timestamp: datetime | None = None
    market: str = "kr_stock"


class MarketDataPort(ABC):
    """Abstract interface for market data retrieval.

    Adapters implement this for each data source.
    """

    @abstractmethod
    async def get_quote(self, symbol: str, **kwargs) -> Quote:
        """Get current price quote for a symbol."""

    @abstractmethod
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        limit: int = 100,
        **kwargs,
    ) -> list[OHLCV]:
        """Get historical OHLCV data.

        timeframe: "1d", "1w", "1mo", "1m", "3m", "5m", "10m", "15m", "30m", "60m"
        """

    @abstractmethod
    async def get_symbols(self, market: str = "kr_stock") -> list[str]:
        """Get available symbols for a given market."""

    async def get_order_book(self, symbol: str, depth: int = 10, **kwargs) -> OrderBook:
        """Get order book (호가창). Optional — adapters may override."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support get_order_book")
