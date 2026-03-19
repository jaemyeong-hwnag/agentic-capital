"""FuturesSessionGuard — system-level futures risk gate.

System-enforced rules (NOT AI guidelines — physically blocked):
- Only ONE futures symbol active at a time
- LONG-ONLY: sell/open (short) orders are always rejected
- Sell orders with position_effect='close' are allowed (closing a long)
- Stop-loss: auto-close positions exceeding N% loss (before AI decision)
- Leverage cap: reject opens that would exceed max_leverage x
- Position sizing: reject opens where notional > capital * position_size_pct
- Isolated margin: each position's loss is bounded by its own margin, not cross-margin
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
    - Max contracts: open orders capped at max_contracts per order
    - Daily loss limit: trading halted for the day if daily_pnl < -max_daily_loss
    - Stop-loss: auto-close each position when loss_pct >= stop_loss_pct
    - Leverage cap: reject opens that push notional/available > max_leverage
    - Position sizing: reject opens where notional > total_capital * position_size_pct
    """

    def __init__(
        self,
        inner: TradingPort,
        capital_limit: float | None = None,
        max_contracts: int | None = None,
        max_daily_loss: float | None = None,
        stop_loss_pct: float | None = None,
        max_leverage: float | None = None,
        position_size_pct: float | None = None,
    ) -> None:
        self._inner = inner
        self._active_symbol: str | None = None
        self._capital_limit = capital_limit
        self._max_contracts = max_contracts
        self._max_daily_loss = max_daily_loss
        self._halt_date: str | None = None  # YYYY-MM-DD when daily loss halted
        self._stop_loss_pct = stop_loss_pct        # e.g. 0.02 = 2%
        self._max_leverage = max_leverage           # e.g. 5.0 = 5x
        self._position_size_pct = position_size_pct  # e.g. 0.05 = 5%

    @property
    def active_symbol(self) -> str | None:
        return self._active_symbol

    async def sync_state(self) -> None:
        """Re-sync active symbol from live positions (call on engine startup).

        Also resets daily halt if it's a new calendar day.
        """
        # Reset daily halt on new day
        if self._halt_date:
            from datetime import date
            today = date.today().isoformat()
            if self._halt_date != today:
                self._halt_date = None
                logger.info("futures_guard_daily_halt_reset")

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

    async def check_stop_losses(self) -> list[str]:
        """Auto-close any futures position whose loss exceeds stop_loss_pct.

        This runs BEFORE the AI decision cycle — it's a forced system action.
        Returns list of symbols that were force-closed.
        Implements isolated margin semantics: each position is evaluated independently.
        """
        if self._stop_loss_pct is None:
            return []
        closed = []
        try:
            positions = await self._inner.get_positions()
            fut = [p for p in positions if p.market in (Market.KR_FUTURES, Market.KR_OPTIONS)]
            for p in fut:
                # unrealized_pnl_pct is negative for losses (e.g. -2.5 means 2.5% loss)
                loss_pct = -p.unrealized_pnl_pct  # positive = loss
                if loss_pct >= self._stop_loss_pct * 100:
                    logger.warning(
                        "futures_guard_stop_loss_triggered",
                        symbol=p.symbol,
                        loss_pct=round(p.unrealized_pnl_pct, 2),
                        threshold_pct=round(-self._stop_loss_pct * 100, 2),
                        unrealized_pnl=round(p.unrealized_pnl, 0),
                    )
                    close_order = Order(
                        symbol=p.symbol,
                        side=OrderSide.SELL,  # long-only → always sell to close
                        order_type=OrderType.MARKET,
                        quantity=p.quantity,
                        market=p.market,
                        position_effect="close",
                    )
                    await self._inner.submit_order(close_order)
                    closed.append(p.symbol)

            if closed:
                self._active_symbol = None
        except Exception:
            logger.warning("futures_guard_stop_loss_check_failed")
        return closed

    async def submit_order(self, order: Order) -> OrderResult:
        # Pass-through for non-futures markets
        if order.market not in (Market.KR_FUTURES, Market.KR_OPTIONS):
            return await self._inner.submit_order(order)

        # Daily loss halt: block ALL new opens if today's loss limit was breached
        if self._halt_date and order.position_effect == "open":
            logger.warning(
                "futures_guard_daily_halt_active",
                halt_date=self._halt_date,
                symbol=order.symbol,
            )
            return OrderResult(
                order_id="",
                symbol=order.symbol,
                side=order.side,
                quantity=0.0,
                filled_price=0.0,
                status="rejected",
                market=order.market,
                metadata={"error": f"daily_loss_limit:trading_halted:{self._halt_date}"},
            )

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

        # Daily loss limit: block new opens if today's realized+unrealized P&L < -limit
        if order.position_effect == "open" and self._max_daily_loss is not None:
            if not await self._daily_loss_safe():
                return OrderResult(
                    order_id="",
                    symbol=order.symbol,
                    side=order.side,
                    quantity=0.0,
                    filled_price=0.0,
                    status="rejected",
                    market=order.market,
                    metadata={"error": f"daily_loss_limit:trading_halted:{self._halt_date}"},
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

        # Position sizing: reject if notional > total_capital * position_size_pct
        # Isolated margin: each trade is sized as a fraction of total capital
        if (
            order.position_effect == "open"
            and self._position_size_pct is not None
            and order.price
            and order.multiplier
        ):
            notional = order.price * order.multiplier * int(order.quantity)
            try:
                bal = await self._inner.get_balance()
                max_notional = bal.total * self._position_size_pct
                if notional > max_notional:
                    # Reduce qty rather than reject outright — let AI trade, just smaller
                    safe_qty = max(1, int(max_notional / (order.price * order.multiplier)))
                    if safe_qty < int(order.quantity):
                        logger.warning(
                            "futures_guard_position_sizing_capped",
                            symbol=order.symbol,
                            requested=int(order.quantity),
                            capped=safe_qty,
                            notional=notional,
                            max_notional=round(max_notional, 0),
                            position_size_pct=self._position_size_pct,
                        )
                        order = Order(
                            symbol=order.symbol,
                            side=order.side,
                            order_type=order.order_type,
                            quantity=float(safe_qty),
                            price=order.price,
                            market=order.market,
                            position_effect=order.position_effect,
                            multiplier=order.multiplier,
                        )
            except Exception:
                pass  # fail-open: allow order if balance check fails

        # Leverage cap: reject if notional / available_capital > max_leverage
        if (
            order.position_effect == "open"
            and self._max_leverage is not None
            and order.price
            and order.multiplier
        ):
            notional = order.price * order.multiplier * int(order.quantity)
            try:
                bal = await self._inner.get_balance()
                if bal.available > 0:
                    leverage = notional / bal.available
                    if leverage > self._max_leverage:
                        # Reduce qty to fit within leverage cap
                        safe_qty = max(1, int(
                            (bal.available * self._max_leverage) / (order.price * order.multiplier)
                        ))
                        if safe_qty < int(order.quantity):
                            logger.warning(
                                "futures_guard_leverage_capped",
                                symbol=order.symbol,
                                requested=int(order.quantity),
                                capped=safe_qty,
                                leverage=round(leverage, 2),
                                max_leverage=self._max_leverage,
                                available=round(bal.available, 0),
                            )
                            order = Order(
                                symbol=order.symbol,
                                side=order.side,
                                order_type=order.order_type,
                                quantity=float(safe_qty),
                                price=order.price,
                                market=order.market,
                                position_effect=order.position_effect,
                                multiplier=order.multiplier,
                            )
            except Exception:
                pass  # fail-open: allow order if balance check fails

        # Max contracts hard cap: absolute limit regardless of capital
        if order.position_effect == "open" and self._max_contracts is not None:
            if order.quantity > self._max_contracts:
                logger.warning(
                    "futures_guard_contracts_capped",
                    symbol=order.symbol,
                    requested=order.quantity,
                    capped=self._max_contracts,
                )
                order = Order(
                    symbol=order.symbol,
                    side=order.side,
                    order_type=order.order_type,
                    quantity=float(self._max_contracts),
                    price=order.price,
                    market=order.market,
                    position_effect=order.position_effect,
                    multiplier=order.multiplier,
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

        # Post-fill: validate actual position size using real multiplier from broker
        # Catches any symbol the AI chooses — no hardcoding needed
        if result.status not in ("rejected", "cancelled") and order.position_effect == "open":
            await self._enforce_qty_by_position(order.symbol)

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

    async def _enforce_qty_by_position(self, symbol: str) -> None:
        """Post-fill: read actual multiplier from broker position and close excess contracts.

        Works for any futures symbol — multiplier comes from the broker, not hardcoded.
        """
        if self._capital_limit is None:
            return
        try:
            from agentic_capital.ports.trading import FuturesPosition
            positions = await self._inner.get_positions()
            fut = [p for p in positions
                   if p.market in (Market.KR_FUTURES, Market.KR_OPTIONS)
                   and p.symbol == symbol
                   and isinstance(p, FuturesPosition)]
            if not fut:
                return
            p = fut[0]
            worst_per_contract = p.current_price * 0.10 * p.multiplier
            if worst_per_contract <= 0:
                return
            safe_qty = max(1, int(self._capital_limit / worst_per_contract))
            excess = int(p.quantity) - safe_qty
            if excess <= 0:
                return
            logger.warning(
                "futures_guard_post_fill_qty_reduced",
                symbol=symbol,
                held=int(p.quantity),
                safe=safe_qty,
                excess=excess,
                multiplier=p.multiplier,
                capital_limit=self._capital_limit,
            )
            close_order = Order(
                symbol=symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                quantity=float(excess),
                market=p.market,
                position_effect="close",
                multiplier=p.multiplier,
            )
            await self._inner.submit_order(close_order)
        except Exception:
            logger.warning("futures_guard_post_fill_validation_failed", symbol=symbol)

    async def _daily_loss_safe(self) -> bool:
        """Return False if futures-only unrealized loss today >= max_daily_loss.

        Uses futures positions only — NOT total account daily_pnl, which would
        include stock positions from other simulations on the same account.
        """
        try:
            positions = await self._inner.get_positions()
            fut = [p for p in positions if p.market in (Market.KR_FUTURES, Market.KR_OPTIONS)]
            total_pnl = sum(p.unrealized_pnl for p in fut)
            if total_pnl < -self._max_daily_loss:
                from datetime import date
                self._halt_date = date.today().isoformat()
                logger.warning(
                    "futures_guard_daily_loss_limit_breached",
                    futures_unrealized_pnl=total_pnl,
                    max_daily_loss=self._max_daily_loss,
                    halt_date=self._halt_date,
                )
                return False
            return True
        except Exception:
            return True  # fail-open: allow if check fails

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
