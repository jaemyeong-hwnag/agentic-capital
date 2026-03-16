"""Paper trading adapter — simulated trading for Phase 1 testing."""

from uuid import uuid4

import structlog

from agentic_capital.ports.trading import (
    Balance,
    Market,
    Order,
    OrderResult,
    OrderSide,
    Position,
    TradingPort,
)

logger = structlog.get_logger()


class PaperTradingAdapter(TradingPort):
    """Simulated trading adapter for paper trading.

    Tracks virtual positions and balance in-memory.
    No real API calls — used for system validation.
    """

    def __init__(self, initial_balance: float = 1_000_000.0) -> None:
        self._balance = initial_balance
        self._positions: dict[str, Position] = {}
        self._orders: dict[str, OrderResult] = {}
        logger.info("paper_trading_initialized", initial_balance=initial_balance)

    async def get_balance(self) -> Balance:
        position_value = sum(p.quantity * p.current_price for p in self._positions.values())
        return Balance(
            total=self._balance + position_value,
            available=self._balance,
            currency="USD",
        )

    async def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    async def submit_order(self, order: Order) -> OrderResult:
        fill_price = order.price if order.price else 0.0
        order_id = str(uuid4())
        logger.info(
            "paper_order_submitted",
            order_id=order_id,
            symbol=order.symbol,
            side=order.side.value,
            quantity=order.quantity,
            price=fill_price,
        )

        if order.side == OrderSide.BUY:
            cost = fill_price * order.quantity
            if cost > self._balance:
                logger.warning(
                    "paper_order_rejected_insufficient_balance",
                    order_id=order_id,
                    symbol=order.symbol,
                    cost=cost,
                    available=self._balance,
                )
                return OrderResult(
                    order_id=order_id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=0.0,
                    filled_price=0.0,
                    status="rejected",
                )
            self._balance -= cost
            if order.symbol in self._positions:
                pos = self._positions[order.symbol]
                total_qty = pos.quantity + order.quantity
                avg = (pos.avg_price * pos.quantity + fill_price * order.quantity) / total_qty
                self._positions[order.symbol] = Position(
                    symbol=order.symbol,
                    quantity=total_qty,
                    avg_price=avg,
                    current_price=fill_price,
                    unrealized_pnl=0.0,
                    unrealized_pnl_pct=0.0,
                    market=order.market,
                    exchange=order.exchange,
                )
            else:
                self._positions[order.symbol] = Position(
                    symbol=order.symbol,
                    quantity=order.quantity,
                    avg_price=fill_price,
                    current_price=fill_price,
                    unrealized_pnl=0.0,
                    unrealized_pnl_pct=0.0,
                    market=order.market,
                    exchange=order.exchange,
                )
        else:  # SELL
            if order.symbol not in self._positions:
                logger.warning(
                    "paper_order_rejected_no_position",
                    order_id=order_id,
                    symbol=order.symbol,
                )
                return OrderResult(
                    order_id=order_id,
                    symbol=order.symbol,
                    side=order.side,
                    quantity=0.0,
                    filled_price=0.0,
                    status="rejected",
                )
            pos = self._positions[order.symbol]
            sell_qty = min(order.quantity, pos.quantity)
            self._balance += fill_price * sell_qty
            remaining = pos.quantity - sell_qty
            if remaining <= 0:
                del self._positions[order.symbol]
            else:
                self._positions[order.symbol] = Position(
                    symbol=order.symbol,
                    quantity=remaining,
                    avg_price=pos.avg_price,
                    current_price=fill_price,
                    unrealized_pnl=(fill_price - pos.avg_price) * remaining,
                    unrealized_pnl_pct=(fill_price - pos.avg_price) / pos.avg_price if pos.avg_price else 0.0,
                )

        result = OrderResult(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            filled_price=fill_price,
            status="filled",
        )
        self._orders[order_id] = result
        logger.info(
            "paper_order_filled",
            order_id=order_id,
            symbol=order.symbol,
            side=order.side.value,
            quantity=order.quantity,
            price=fill_price,
            balance=self._balance,
        )
        return result

    async def get_order_status(self, order_id: str) -> OrderResult:
        if order_id not in self._orders:
            return OrderResult(
                order_id=order_id,
                symbol="",
                side=OrderSide.BUY,
                quantity=0.0,
                filled_price=0.0,
                status="not_found",
            )
        return self._orders[order_id]
