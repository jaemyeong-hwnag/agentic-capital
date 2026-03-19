"""Virtual futures adapter — local simulation when KIS paper trading lacks futures support.

KIS paper trading (모의투자) for futures/options requires separate account registration
(선물옵션 모의투자 별도 신청). When that's not available, this adapter simulates futures
trading locally using Yahoo Finance prices for mark-to-market P&L.

Architecture: wraps an inner TradingPort (KIS) for non-futures ops, handles futures
orders locally.
"""

from __future__ import annotations

from uuid import uuid4

import structlog

from agentic_capital.ports.trading import (
    Balance,
    FuturesPosition,
    Market,
    Order,
    OrderResult,
    OrderSide,
    TradingPort,
)

logger = structlog.get_logger()

_FUTURES_MARKETS = {Market.KR_FUTURES, Market.KR_OPTIONS}
_KOSPI200_STANDARD_MULT = 250_000
_KOSPI200_MINI_MULT = 50_000


def _multiplier_for(symbol: str) -> float:
    if symbol.startswith("105"):
        return _KOSPI200_MINI_MULT
    return _KOSPI200_STANDARD_MULT


async def _fetch_kospi200_price() -> float:
    """Fetch KOSPI200 index via Yahoo Finance (no auth required)."""
    from agentic_capital.adapters.trading.kis import _fetch_yfinance_kospi200
    d = await _fetch_yfinance_kospi200()
    return d.get("price", 0.0) if d else 0.0


class _VirtualFuturesPosition:
    """In-memory futures position for virtual simulation."""

    def __init__(self, symbol: str, side: str, quantity: float,
                 avg_price: float, multiplier: float) -> None:
        self.symbol = symbol
        self.side = side           # "long" | "short"
        self.quantity = quantity
        self.avg_price = avg_price
        self.multiplier = multiplier
        self.current_price = avg_price

    def update_price(self, price: float) -> None:
        self.current_price = price

    @property
    def unrealized_pnl(self) -> float:
        direction = 1.0 if self.side == "long" else -1.0
        return direction * (self.current_price - self.avg_price) * self.multiplier * self.quantity

    @property
    def margin_required(self) -> float:
        # 3% of notional ≈ KRX basic deposit requirement (기본예탁금)
        # Lower than full initial margin to allow simulation within small capital.
        return self.avg_price * self.multiplier * self.quantity * 0.03

    def to_port(self) -> FuturesPosition:
        return FuturesPosition(
            symbol=self.symbol,
            quantity=self.quantity,
            avg_price=self.avg_price,
            current_price=self.current_price,
            unrealized_pnl=self.unrealized_pnl,
            unrealized_pnl_pct=(
                (self.current_price - self.avg_price) / self.avg_price * 100
                if self.avg_price > 0 else 0.0
            ),
            market=Market.KR_FUTURES,
            currency="KRW",
            multiplier=self.multiplier,
            margin_required=self.margin_required,
            net_side=self.side,
        )


class FuturesVirtualAdapter(TradingPort):
    """Virtual futures trading adapter for paper simulation.

    - Non-futures ops delegated to inner (KIS) adapter
    - Futures orders filled locally at current Yahoo Finance price
    - Balance = initial_capital +/- realized P&L from closed positions
    """

    def __init__(self, inner: TradingPort, initial_capital: float = 1_500_000.0) -> None:
        self._inner = inner
        self._capital = initial_capital         # cash pool
        self._positions: dict[str, _VirtualFuturesPosition] = {}
        self._realized_pnl = 0.0
        logger.info(
            "futures_virtual_adapter_started",
            initial_capital=initial_capital,
        )

    # ── Balance ───────────────────────────────────────────────────────────────

    async def get_balance(self) -> Balance:
        price = await _fetch_kospi200_price()
        for pos in self._positions.values():
            pos.update_price(price)

        unrealized = sum(p.unrealized_pnl for p in self._positions.values())
        margin_used = sum(p.margin_required for p in self._positions.values())
        available = self._capital - margin_used
        return Balance(
            total=self._capital + unrealized,
            available=max(available, 0.0),
            currency="KRW",
            daily_pnl=unrealized + self._realized_pnl,
        )

    # ── Positions ─────────────────────────────────────────────────────────────

    async def get_positions(self) -> list:
        price = await _fetch_kospi200_price()
        for pos in self._positions.values():
            pos.update_price(price)

        # Virtual futures + real stock positions from inner
        try:
            real = await self._inner.get_positions()
            stock = [p for p in real if p.market not in _FUTURES_MARKETS]
        except Exception:
            stock = []

        return stock + [p.to_port() for p in self._positions.values()]

    # ── Order submission ──────────────────────────────────────────────────────

    async def submit_order(self, order: Order) -> OrderResult:
        if order.market not in _FUTURES_MARKETS:
            return await self._inner.submit_order(order)
        return await self._submit_virtual_futures_order(order)

    @staticmethod
    def _is_valid_kospi200_symbol(symbol: str) -> bool:
        """Validate KOSPI200 standard/mini futures symbol format: 101/105 + CFIL + digit."""
        import re
        return bool(re.fullmatch(r"(101|105)[CFIL]\d", symbol))

    async def _submit_virtual_futures_order(self, order: Order) -> OrderResult:
        if not self._is_valid_kospi200_symbol(order.symbol):
            logger.warning(
                "futures_virtual_invalid_symbol",
                symbol=order.symbol,
                hint="Use 101/105 + month_code(C/F/I/L) + year_digit. Call get_futures_symbols() first.",
            )
            return OrderResult(
                order_id="", symbol=order.symbol, side=order.side,
                quantity=0.0, filled_price=0.0, status="rejected",
                market=order.market,
                metadata={"error": f"invalid_symbol:{order.symbol} — call get_futures_symbols() for valid symbols"},
            )

        fill_price = await _fetch_kospi200_price()
        if fill_price <= 0:
            logger.warning("futures_virtual_no_price", symbol=order.symbol)
            return OrderResult(
                order_id="", symbol=order.symbol, side=order.side,
                quantity=0.0, filled_price=0.0, status="rejected",
                market=order.market,
                metadata={"error": "no_price_data"},
            )

        mult = order.multiplier or _multiplier_for(order.symbol)
        order_id = str(uuid4())[:8]
        qty = int(order.quantity)

        if order.position_effect == "open":
            margin_needed = fill_price * mult * qty * 0.03  # 3% = KRX 기본예탁금
            bal = await self.get_balance()
            if bal.available < margin_needed:
                logger.warning(
                    "futures_virtual_insufficient_margin",
                    symbol=order.symbol, needed=margin_needed, available=bal.available,
                )
                return OrderResult(
                    order_id="", symbol=order.symbol, side=order.side,
                    quantity=0.0, filled_price=0.0, status="rejected",
                    market=order.market,
                    metadata={"error": "insufficient_margin"},
                )
            side = "long" if order.side == OrderSide.BUY else "short"
            if order.symbol in self._positions:
                # Add to existing position (same side)
                existing = self._positions[order.symbol]
                total_qty = existing.quantity + qty
                existing.avg_price = (
                    (existing.avg_price * existing.quantity + fill_price * qty) / total_qty
                )
                existing.quantity = total_qty
            else:
                self._positions[order.symbol] = _VirtualFuturesPosition(
                    symbol=order.symbol, side=side, quantity=qty,
                    avg_price=fill_price, multiplier=mult,
                )
            logger.info(
                "futures_virtual_order_filled",
                order_id=order_id, symbol=order.symbol,
                side=order.side.value, qty=qty, price=fill_price,
                effect="open",
            )

        elif order.position_effect == "close":
            pos = self._positions.get(order.symbol)
            if not pos:
                return OrderResult(
                    order_id="", symbol=order.symbol, side=order.side,
                    quantity=0.0, filled_price=0.0, status="rejected",
                    market=order.market,
                    metadata={"error": "no_position_to_close"},
                )
            close_qty = min(qty, pos.quantity)
            direction = 1.0 if pos.side == "long" else -1.0
            realized = direction * (fill_price - pos.avg_price) * mult * close_qty
            self._realized_pnl += realized

            if close_qty >= pos.quantity:
                del self._positions[order.symbol]
            else:
                pos.quantity -= close_qty

            logger.info(
                "futures_virtual_order_filled",
                order_id=order_id, symbol=order.symbol,
                side=order.side.value, qty=close_qty, price=fill_price,
                effect="close", realized_pnl=realized,
            )
        else:
            return OrderResult(
                order_id="", symbol=order.symbol, side=order.side,
                quantity=0.0, filled_price=0.0, status="rejected",
                market=order.market,
                metadata={"error": f"unknown_position_effect:{order.position_effect}"},
            )

        return OrderResult(
            order_id=order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=qty,
            filled_price=fill_price,
            status="filled",
            market=order.market,
        )

    # ── Delegation ────────────────────────────────────────────────────────────

    async def get_order_status(self, order_id: str) -> OrderResult:
        return await self._inner.get_order_status(order_id)

    async def cancel_order(self, order_id: str, **kwargs) -> bool:
        return await self._inner.cancel_order(order_id, **kwargs)

    async def get_fills(self, start_date=None, end_date=None, symbol=""):
        return await self._inner.get_fills(start_date, end_date, symbol)

    def get_active_futures_contracts(self):
        # Delegate to inner if it has this method (KIS adapter)
        if hasattr(self._inner, "get_active_futures_contracts"):
            return self._inner.get_active_futures_contracts()
        return []

    def get_futures_quote(self, symbol: str):
        if hasattr(self._inner, "get_futures_quote"):
            return self._inner.get_futures_quote(symbol)
        return {}
