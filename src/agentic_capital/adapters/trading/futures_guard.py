"""FuturesSessionGuard — single-symbol lock + long-only enforcement.

System-enforced rules (NOT AI guidelines — physically blocked):
- Only ONE futures symbol active at a time
- LONG-ONLY: sell/open (short) orders are always rejected
- Sell orders with position_effect='close' are allowed (closing a long)
"""

from __future__ import annotations

import structlog

from agentic_capital.ports.trading import (
    Balance,
    Market,
    Order,
    OrderResult,
    Position,
    TradingPort,
)

logger = structlog.get_logger()


class FuturesSessionGuard(TradingPort):
    """Decorator around TradingPort that enforces single-symbol futures trading.

    Rules:
    - Only one futures symbol allowed at a time (_active_symbol lock)
    - Cross-symbol orders are rejected: must close all first
    - Non-futures orders pass through unchanged
    - Call sync_state() on startup to restore lock from live positions
    """

    def __init__(self, inner: TradingPort) -> None:
        self._inner = inner
        self._active_symbol: str | None = None

    @property
    def active_symbol(self) -> str | None:
        return self._active_symbol

    async def sync_state(self) -> None:
        """Re-sync active symbol from live positions (call on engine startup)."""
        try:
            positions = await self._inner.get_positions()
            fut_pos = [p for p in positions if p.market in (Market.KR_FUTURES, Market.KR_OPTIONS)]
            if fut_pos:
                self._active_symbol = fut_pos[0].symbol
                logger.info("futures_guard_synced", active_symbol=self._active_symbol)
            else:
                self._active_symbol = None
                logger.info("futures_guard_synced", active_symbol=None)
        except Exception:
            self._active_symbol = None
            logger.warning("futures_guard_sync_failed_defaulting_unlocked")

    async def submit_order(self, order: Order) -> OrderResult:
        # Pass-through for non-futures markets
        if order.market not in (Market.KR_FUTURES, Market.KR_OPTIONS):
            return await self._inner.submit_order(order)

        # Long-only: reject sell/open (short entry) — sell/close is allowed
        if order.side.value == "sell" and order.position_effect != "close":
            logger.warning(
                "futures_guard_short_blocked",
                symbol=order.symbol,
                side=order.side.value,
                position_effect=order.position_effect,
            )
            return OrderResult(
                order_id="",
                symbol=order.symbol,
                side=order.side,
                quantity=0.0,
                filled_price=0.0,
                status="rejected",
                market=order.market,
                metadata={"error": "long_only:short_positions_not_allowed"},
            )

        # Enforce single-symbol lock
        if self._active_symbol and self._active_symbol != order.symbol:
            logger.warning(
                "futures_guard_symbol_blocked",
                attempted=order.symbol,
                active=self._active_symbol,
            )
            return OrderResult(
                order_id="",
                symbol=order.symbol,
                side=order.side,
                quantity=0.0,
                filled_price=0.0,
                status="rejected",
                market=order.market,
                metadata={"error": f"symbol_lock:{self._active_symbol}:close_all_first"},
            )

        result = await self._inner.submit_order(order)

        # Update lock state after successful order
        if result.status not in ("rejected", "cancelled"):
            if order.position_effect == "close":
                # After close, check if flat to release lock
                try:
                    positions = await self._inner.get_positions()
                    fut_pos = [p for p in positions
                               if p.market in (Market.KR_FUTURES, Market.KR_OPTIONS)]
                    if not fut_pos:
                        self._active_symbol = None
                        logger.info("futures_guard_unlocked", symbol=order.symbol)
                except Exception:
                    pass
            else:
                # Opening or adding — set lock
                self._active_symbol = order.symbol

        return result

    # ── Delegate all other methods ────────────────────────────────────────────

    async def get_balance(self) -> Balance:
        return await self._inner.get_balance()

    async def get_positions(self) -> list[Position]:
        return await self._inner.get_positions()

    async def get_order_status(self, order_id: str) -> OrderResult:
        return await self._inner.get_order_status(order_id)

    async def cancel_order(self, order_id: str, **kwargs) -> bool:
        return await self._inner.cancel_order(order_id, **kwargs)

    async def get_fills(self, start_date=None, end_date=None, symbol=""):
        return await self._inner.get_fills(start_date=start_date, end_date=end_date, symbol=symbol)

    # Delegate any extra methods the inner adapter has
    def __getattr__(self, name: str):
        return getattr(self._inner, name)
