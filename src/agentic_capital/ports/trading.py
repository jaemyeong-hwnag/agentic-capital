"""Trading port — abstract interface for order execution."""

from abc import ABC, abstractmethod
from enum import StrEnum

from pydantic import BaseModel


class Market(StrEnum):
    """Markets supported by KIS and other adapters."""
    KR_STOCK = "kr_stock"      # 국내주식 (KOSPI/KOSDAQ)
    US_STOCK = "us_stock"      # 미국주식 (NYSE/NASDAQ/AMEX)
    HK_STOCK = "hk_stock"      # 홍콩주식
    CN_STOCK = "cn_stock"      # 중국주식 (상하이/선전)
    JP_STOCK = "jp_stock"      # 일본주식
    VN_STOCK = "vn_stock"      # 베트남주식
    KR_FUTURES = "kr_futures"  # 국내선물
    KR_OPTIONS = "kr_options"  # 국내옵션


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
    price: float | None = None          # Required for limit orders
    market: Market = Market.KR_STOCK    # Which market to trade
    exchange: str | None = None         # Exchange code for overseas: "NASD", "NYSE", "AMEX", "SEHK", etc.


class OrderResult(BaseModel):
    """Result of an executed order."""

    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    filled_price: float
    status: str                         # filled, partial, rejected, submitted, cancelled
    market: Market = Market.KR_STOCK
    metadata: dict = {}                 # Exchange-specific data (e.g., KRX_FWDG_ORD_ORGNO for KIS cancel)


class Balance(BaseModel):
    """Account balance."""

    total: float
    available: float
    currency: str = "USD"
    daily_pnl: float = 0.0      # today's P&L (positive = profit, negative = loss)
    daily_fee: float = 0.0      # today's commissions + taxes paid


class Position(BaseModel):
    """A held position."""

    symbol: str
    quantity: float
    avg_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    market: Market = Market.KR_STOCK
    exchange: str | None = None         # Exchange code for overseas positions
    currency: str = "KRW"


class TradingPort(ABC):
    """Abstract interface for trading operations.

    Adapters implement this for each exchange/broker.
    Swappable without changing Core logic.
    """

    @abstractmethod
    async def get_balance(self) -> Balance:
        """Get account balance (primary currency)."""

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Get all open positions across all markets."""

    @abstractmethod
    async def submit_order(self, order: Order) -> OrderResult:
        """Submit an order for execution."""

    @abstractmethod
    async def get_order_status(self, order_id: str) -> OrderResult:
        """Check status of a submitted order."""

    async def cancel_order(self, order_id: str, **kwargs) -> bool:
        """Cancel a pending order. Optional — adapters may override."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support cancel_order")

    async def get_fills(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        symbol: str = "",
    ) -> list[OrderResult]:
        """Get order fill history. Optional — adapters may override."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support get_fills")
