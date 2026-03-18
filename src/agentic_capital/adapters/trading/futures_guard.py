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
    OrderSide,
    OrderType,
    Position,
    TradingPort,
)

logger = structlog.get_logger()


class FuturesSessionGuard(TradingPort):
    """Decorator around TradingPort that enforces futures trading rules.

    System-enforced rules (NOT AI guidelines — physically blocked):
    - Long-only: sell/open (short entry) always rejected
    - Single-symbol lock: cross-symbol orders rejected until close_all
    - Capital limit: open orders rejected when unrealized loss >= capital_limit;
      enforce_capital_limit() force-closes all positions if limit is breached
    """

    def __init__(self, inner: TradingPort, capital_limit: float | None = None) -> None:
        self._inner = inner
        self._active_symbol: str | None = None
        self._capital_limit = capital_limit

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

        # Capital limit: block new opens if unrealized loss already >= limit
        if order.position_effect == "open" and self._capital_limit is not None:
            if not await self._capital_safe():
                logger.warning(
                    "futures_guard_capital_limit_blocked",
                    capital_limit=self._capital_limit,
                )
                return OrderResult(
                    order_id="",
                    symbol=order.symbol,
                    side=order.side,
                    quantity=0.0,
                    filled_price=0.0,
                    status="rejected",
                    market=order.market,
                    metadata={"error": "capital_limit_exceeded:close_positions_first"},
                )

        # Max quantity guard: cap contracts so worst-case 10% drop <= capital_limit
        # Only applies when both price and multiplier are known on the order.
        # If multiplier is unknown, skip cap and rely on PnL-based checks instead.
        if (
            order.position_effect == "open"
            and self._capital_limit is not None
            and order.price
            and order.multiplier
        ):
            worst_loss_per_contract = order.price * 0.10 * order.multiplier
            if worst_loss_per_contract > 0:
                max_qty = max(1, int(self._capital_limit / worst_loss_per_contract))
                if order.quantity > max_qty:
                    logger.warning(
                        "futures_guard_qty_capped",
                        symbol=order.symbol,
                        requested=order.quantity,
                        capped=max_qty,
                        multiplier=order.multiplier,
                        capital_limit=self._capital_limit,
                    )
                    order = Order(
                        symbol=order.symbol,
                        side=order.side,
                        order_type=order.order_type,
                        quantity=float(max_qty),
                        price=order.price,
                        market=order.market,
                        position_effect=order.position_effect,
                        multiplier=order.multiplier,
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

    async def _capital_safe(self) -> bool:
        """Return False if total unrealized loss >= capital_limit."""
        try:
            positions = await self._inner.get_positions()
            fut = [p for p in positions if p.market in (Market.KR_FUTURES, Market.KR_OPTIONS)]
            total_loss = sum(p.unrealized_pnl for p in fut if p.unrealized_pnl < 0)
            return abs(total_loss) < self._capital_limit
        except Exception:
            return True  # fail-open: allow if check fails

    async def enforce_capital_limit(self) -> bool:
        """Force-close all futures positions if unrealized loss >= capital_limit.

        Called by engine at start of each cycle. Returns True if positions were closed.
        """
        if self._capital_limit is None:
            return False
        try:
            positions = await self._inner.get_positions()
            fut = [p for p in positions if p.market in (Market.KR_FUTURES, Market.KR_OPTIONS)]
            if not fut:
                return False
            total_loss = sum(p.unrealized_pnl for p in fut if p.unrealized_pnl < 0)
            if abs(total_loss) < self._capital_limit:
                return False

            logger.warning(
                "futures_capital_limit_breached_force_closing",
                total_loss=total_loss,
                capital_limit=self._capital_limit,
            )
            for p in fut:
                order = Order(
                    symbol=p.symbol,
                    side=OrderSide.SELL,  # long-only → always sell to close
                    order_type=OrderType.MARKET,
                    quantity=p.quantity,
                    market=p.market,
                    position_effect="close",
                )
                await self._inner.submit_order(order)  # bypass guard, direct to inner
            self._active_symbol = None
            return True
        except Exception:
            logger.warning("futures_capital_limit_enforce_failed")
            return False

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
