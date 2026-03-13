"""Trading port — abstract interface for order execution."""

from abc import ABC, abstractmethod
from enum import StrEnum

from pydantic import BaseModel


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


class Order(BaseModel):
    """Order request."""

    symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    quantity: float
    price: float | None = None  # Required for limit orders


class OrderResult(BaseModel):
    """Result of an executed order."""

    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    filled_price: float
    status: str  # filled, partial, rejected


class Balance(BaseModel):
    """Account balance."""

    total: float
    available: float
    currency: str = "USD"


class Position(BaseModel):
    """A held position."""

    symbol: str
    quantity: float
    avg_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


class TradingPort(ABC):
    """Abstract interface for trading operations.

    Adapters implement this for each exchange/broker.
    Swappable without changing Core logic.
    """

    @abstractmethod
    async def get_balance(self) -> Balance:
        """Get account balance."""

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Get all open positions."""

    @abstractmethod
    async def submit_order(self, order: Order) -> OrderResult:
        """Submit an order for execution."""

    @abstractmethod
    async def get_order_status(self, order_id: str) -> OrderResult:
        """Check status of a submitted order."""
