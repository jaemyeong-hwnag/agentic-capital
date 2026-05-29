"""Trading port — abstract interface for order execution."""

from abc import ABC, abstractmethod
from enum import StrEnum
import re

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
    position_effect: str | None = None  # Futures only: "open" (신규) | "close" (청산)
    multiplier: float | None = None     # Futures: KRW per point (e.g. 250000 for KOSPI200, 50000 for mini). None = unknown.
    option_type: str | None = None      # Options only: "call" allowed by policy; puts are rejected.


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


class FuturesPosition(Position):
    """A futures/options position with margin and contract info."""

    multiplier: float = 250_000    # KRW per point — must be set per contract (KOSPI200=250000, mini=50000, etc.)
    margin_required: float = 0.0   # initial margin in KRW
    expiry: str | None = None      # contract expiry YYYYMM
    net_side: str = "long"         # "long" | "short"
    pnl_per_contract: float = 0.0  # P&L in KRW per contract


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


def infer_option_type(
    symbol: str,
    option_type: str | None = None,
    exchange: str | None = None,
) -> str | None:
    """Infer option type from explicit metadata or AI-friendly paper symbols.

    The project allows only call options. Because KIS compact option symbols are
    broker-specific and not always self-describing in local tests, the safest
    contract is explicit metadata (`option_type="call"` or `exchange="CALL"`).
    Paper-loop symbols may also include clear CALL/PUT markers.
    """
    explicit = str(option_type or "").strip().lower()
    if explicit in {"call", "c", "콜", "콜옵션"}:
        return "call"
    if explicit in {"put", "p", "풋", "풋옵션"}:
        return "put"

    exchange_marker = str(exchange or "").strip().lower()
    if exchange_marker in {"call", "call_option", "kr_call", "krx_call"}:
        return "call"
    if exchange_marker in {"put", "put_option", "kr_put", "krx_put"}:
        return "put"

    sym = str(symbol or "").strip().upper()
    if re.search(r"(^|[_:\-])PUT($|[_:\-])", sym) or re.fullmatch(r"(K200|KOSPI200)?P[0-9A-Z._-]+", sym):
        return "put"
    if re.search(r"(^|[_:\-])CALL($|[_:\-])", sym) or re.fullmatch(r"(K200|KOSPI200)?C[0-9A-Z._-]+", sym):
        return "call"
    return None


def is_call_option_order(order: Order) -> bool:
    """Return True only for orders explicitly known to be call options."""
    return infer_option_type(order.symbol, order.option_type, order.exchange) == "call"
