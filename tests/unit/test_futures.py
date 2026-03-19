"""Tests for futures trading components: FuturesSessionGuard, futures_tools, FuturesEngine."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_capital.adapters.trading.futures_guard import FuturesSessionGuard
from agentic_capital.ports.trading import (
    Balance,
    FuturesPosition,
    Market,
    Order,
    OrderResult,
    OrderSide,
    OrderType,
    Position,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_inner() -> MagicMock:
    inner = MagicMock()
    inner.submit_order = AsyncMock(return_value=OrderResult(
        order_id="OID1",
        symbol="101W6",
        side=OrderSide.BUY,
        quantity=1.0,
        filled_price=380.0,
        status="filled",
        market=Market.KR_FUTURES,
    ))
    inner.get_positions = AsyncMock(return_value=[])
    inner.get_balance = AsyncMock(return_value=Balance(
        total=10_000_000, available=8_000_000, currency="KRW",
        daily_pnl=0.0, daily_fee=0.0,
    ))
    inner.get_order_status = AsyncMock()
    inner.cancel_order = AsyncMock(return_value=True)
    inner.get_fills = AsyncMock(return_value=[])
    return inner


def _futures_order(symbol: str = "101W6", effect: str = "open") -> Order:
    return Order(
        symbol=symbol,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=1.0,
        market=Market.KR_FUTURES,
        position_effect=effect,
    )


def _futures_position(symbol: str = "101W6") -> FuturesPosition:
    return FuturesPosition(
        symbol=symbol,
        quantity=1.0,
        avg_price=380.0,
        current_price=381.0,
        unrealized_pnl=250_000.0,
        unrealized_pnl_pct=0.26,
        market=Market.KR_FUTURES,
        currency="KRW",
    )


# ── FuturesSessionGuard ───────────────────────────────────────────────────────


class TestFuturesSessionGuard:
    @pytest.mark.asyncio
    async def test_initial_state_unlocked(self):
        guard = FuturesSessionGuard(_mock_inner())
        assert guard.active_symbol is None

    @pytest.mark.asyncio
    async def test_open_order_sets_lock(self):
        guard = FuturesSessionGuard(_mock_inner())
        result = await guard.submit_order(_futures_order("101W6", "open"))
        assert result.status == "filled"
        assert guard.active_symbol == "101W6"

    @pytest.mark.asyncio
    async def test_same_symbol_allowed_while_locked(self):
        guard = FuturesSessionGuard(_mock_inner())
        await guard.submit_order(_futures_order("101W6", "open"))
        # Same symbol again
        result = await guard.submit_order(_futures_order("101W6", "open"))
        assert result.status == "filled"

    @pytest.mark.asyncio
    async def test_different_symbol_rejected_while_locked(self):
        guard = FuturesSessionGuard(_mock_inner())
        await guard.submit_order(_futures_order("101W6", "open"))
        result = await guard.submit_order(_futures_order("101W7", "open"))
        assert result.status == "rejected"
        assert "symbol_lock" in result.metadata["error"]
        assert "101W6" in result.metadata["error"]

    @pytest.mark.asyncio
    async def test_short_open_rejected(self):
        """sell/open (short entry) must always be rejected — long-only."""
        guard = FuturesSessionGuard(_mock_inner())
        short_order = Order(
            symbol="101W6",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=1.0,
            market=Market.KR_FUTURES,
            position_effect="open",
        )
        result = await guard.submit_order(short_order)
        assert result.status == "rejected"
        assert "long_only" in result.metadata["error"]

    @pytest.mark.asyncio
    async def test_sell_close_allowed(self):
        """sell/close (청산) must be allowed — only closing a long."""
        guard = FuturesSessionGuard(_mock_inner())
        guard._active_symbol = "101W6"
        close_order = Order(
            symbol="101W6",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=1.0,
            market=Market.KR_FUTURES,
            position_effect="close",
        )
        result = await guard.submit_order(close_order)
        assert result.status == "filled"

    @pytest.mark.asyncio
    async def test_close_order_releases_lock_when_flat(self):
        inner = _mock_inner()
        inner.get_positions = AsyncMock(return_value=[])  # flat after close
        guard = FuturesSessionGuard(inner)
        guard._active_symbol = "101W6"

        close_order = Order(
            symbol="101W6",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=1.0,
            market=Market.KR_FUTURES,
            position_effect="close",
        )
        inner.submit_order.return_value = OrderResult(
            order_id="OID2", symbol="101W6", side=OrderSide.SELL,
            quantity=1.0, filled_price=381.0, status="filled",
            market=Market.KR_FUTURES,
        )
        await guard.submit_order(close_order)
        assert guard.active_symbol is None

    @pytest.mark.asyncio
    async def test_close_order_keeps_lock_when_still_positioned(self):
        inner = _mock_inner()
        inner.get_positions = AsyncMock(return_value=[_futures_position("101W6")])
        guard = FuturesSessionGuard(inner)
        guard._active_symbol = "101W6"

        close_order = Order(
            symbol="101W6",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=1.0,
            market=Market.KR_FUTURES,
            position_effect="close",
        )
        inner.submit_order.return_value = OrderResult(
            order_id="OID2", symbol="101W6", side=OrderSide.SELL,
            quantity=1.0, filled_price=381.0, status="filled",
            market=Market.KR_FUTURES,
        )
        await guard.submit_order(close_order)
        assert guard.active_symbol == "101W6"  # still locked

    @pytest.mark.asyncio
    async def test_rejected_order_does_not_change_lock(self):
        inner = _mock_inner()
        inner.submit_order.return_value = OrderResult(
            order_id="", symbol="101W6", side=OrderSide.BUY,
            quantity=0.0, filled_price=0.0, status="rejected",
            market=Market.KR_FUTURES,
        )
        guard = FuturesSessionGuard(inner)
        await guard.submit_order(_futures_order("101W6", "open"))
        assert guard.active_symbol is None  # rejected didn't lock

    @pytest.mark.asyncio
    async def test_non_futures_order_passes_through(self):
        inner = _mock_inner()
        inner.submit_order.return_value = OrderResult(
            order_id="OID3", symbol="005930", side=OrderSide.BUY,
            quantity=1.0, filled_price=83_800.0, status="filled",
            market=Market.KR_STOCK,
        )
        guard = FuturesSessionGuard(inner)
        guard._active_symbol = "101W6"  # locked on futures

        stock_order = Order(
            symbol="005930",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            market=Market.KR_STOCK,
        )
        result = await guard.submit_order(stock_order)
        assert result.status == "filled"
        assert guard.active_symbol == "101W6"  # unchanged

    @pytest.mark.asyncio
    async def test_sync_state_sets_active_symbol(self):
        inner = _mock_inner()
        inner.get_positions = AsyncMock(return_value=[_futures_position("101W6")])
        guard = FuturesSessionGuard(inner)
        await guard.sync_state()
        assert guard.active_symbol == "101W6"

    @pytest.mark.asyncio
    async def test_sync_state_clears_when_no_positions(self):
        inner = _mock_inner()
        inner.get_positions = AsyncMock(return_value=[])
        guard = FuturesSessionGuard(inner)
        guard._active_symbol = "101W6"
        await guard.sync_state()
        assert guard.active_symbol is None

    @pytest.mark.asyncio
    async def test_sync_state_on_exception_defaults_unlocked(self):
        inner = _mock_inner()
        inner.get_positions = AsyncMock(side_effect=Exception("timeout"))
        guard = FuturesSessionGuard(inner)
        guard._active_symbol = "101W6"
        await guard.sync_state()
        assert guard.active_symbol is None

    @pytest.mark.asyncio
    async def test_delegate_get_balance(self):
        inner = _mock_inner()
        guard = FuturesSessionGuard(inner)
        bal = await guard.get_balance()
        assert bal.total == 10_000_000

    @pytest.mark.asyncio
    async def test_delegate_get_positions(self):
        inner = _mock_inner()
        inner.get_positions = AsyncMock(return_value=[_futures_position()])
        guard = FuturesSessionGuard(inner)
        pos = await guard.get_positions()
        assert len(pos) == 1

    @pytest.mark.asyncio
    async def test_getattr_delegates_to_inner(self):
        inner = _mock_inner()
        inner.get_futures_quote = AsyncMock(return_value={"price": 380.0})
        guard = FuturesSessionGuard(inner)
        result = await guard.get_futures_quote("101W6")
        assert result["price"] == 380.0

    # ── Max contracts ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_max_contracts_caps_quantity(self):
        """Open order exceeding max_contracts is silently capped, not rejected."""
        inner = _mock_inner()
        guard = FuturesSessionGuard(inner, max_contracts=3)
        order = Order(
            symbol="101W6",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10.0,  # exceeds cap
            market=Market.KR_FUTURES,
            position_effect="open",
        )
        result = await guard.submit_order(order)
        assert result.status == "filled"
        submitted = inner.submit_order.call_args[0][0]
        assert submitted.quantity == 3.0  # capped

    @pytest.mark.asyncio
    async def test_max_contracts_close_not_capped(self):
        """Close orders are never subject to max_contracts cap."""
        inner = _mock_inner()
        guard = FuturesSessionGuard(inner, max_contracts=3)
        guard._active_symbol = "101W6"
        order = Order(
            symbol="101W6",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=10.0,  # large close — must not be capped
            market=Market.KR_FUTURES,
            position_effect="close",
        )
        result = await guard.submit_order(order)
        assert result.status == "filled"
        submitted = inner.submit_order.call_args[0][0]
        assert submitted.quantity == 10.0  # unchanged

    @pytest.mark.asyncio
    async def test_max_contracts_within_limit_unchanged(self):
        """Orders within max_contracts are passed through unchanged."""
        inner = _mock_inner()
        guard = FuturesSessionGuard(inner, max_contracts=3)
        order = Order(
            symbol="101W6",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=2.0,
            market=Market.KR_FUTURES,
            position_effect="open",
        )
        await guard.submit_order(order)
        submitted = inner.submit_order.call_args[0][0]
        assert submitted.quantity == 2.0

    # ── Daily loss limit ───────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_daily_loss_limit_blocks_open_when_breached(self):
        """Open order rejected when futures unrealized P&L < -max_daily_loss."""
        inner = _mock_inner()
        # Futures position with large unrealized loss
        inner.get_positions = AsyncMock(return_value=[
            FuturesPosition(
                symbol="101W6", quantity=1.0, avg_price=380.0,
                current_price=355.0,  # large drop
                unrealized_pnl=-60_000.0,  # exceeds 50K limit
                unrealized_pnl_pct=-6.0,
                market=Market.KR_FUTURES, currency="KRW",
            )
        ])
        guard = FuturesSessionGuard(inner, max_daily_loss=50_000.0)
        result = await guard.submit_order(_futures_order("101W6", "open"))
        assert result.status == "rejected"
        assert "daily_loss_limit" in result.metadata["error"]

    @pytest.mark.asyncio
    async def test_daily_loss_sets_halt_date(self):
        """Breaching daily loss sets _halt_date to today."""
        from datetime import date
        inner = _mock_inner()
        inner.get_positions = AsyncMock(return_value=[
            FuturesPosition(
                symbol="101W6", quantity=1.0, avg_price=380.0,
                current_price=355.0, unrealized_pnl=-60_000.0,
                unrealized_pnl_pct=-6.0,
                market=Market.KR_FUTURES, currency="KRW",
            )
        ])
        guard = FuturesSessionGuard(inner, max_daily_loss=50_000.0)
        await guard.submit_order(_futures_order("101W6", "open"))
        assert guard._halt_date == date.today().isoformat()

    @pytest.mark.asyncio
    async def test_daily_halt_flag_blocks_subsequent_opens(self):
        """Once halted, subsequent open orders are blocked without calling balance."""
        inner = _mock_inner()
        guard = FuturesSessionGuard(inner, max_daily_loss=50_000.0)
        from datetime import date
        guard._halt_date = date.today().isoformat()  # pre-set halt

        result = await guard.submit_order(_futures_order("101W6", "open"))
        assert result.status == "rejected"
        assert "daily_loss_limit" in result.metadata["error"]
        inner.get_balance.assert_not_called()  # fast-path, no balance call

    @pytest.mark.asyncio
    async def test_daily_halt_allows_close_orders(self):
        """Close orders bypass the daily halt — allow liquidation even when halted."""
        inner = _mock_inner()
        guard = FuturesSessionGuard(inner, max_daily_loss=50_000.0)
        from datetime import date
        guard._halt_date = date.today().isoformat()
        guard._active_symbol = "101W6"

        close_order = Order(
            symbol="101W6",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=1.0,
            market=Market.KR_FUTURES,
            position_effect="close",
        )
        result = await guard.submit_order(close_order)
        assert result.status == "filled"  # close always allowed

    @pytest.mark.asyncio
    async def test_daily_halt_resets_on_new_day_via_sync_state(self):
        """sync_state() resets the halt flag if it was set on a prior day."""
        inner = _mock_inner()
        guard = FuturesSessionGuard(inner, max_daily_loss=50_000.0)
        guard._halt_date = "2000-01-01"  # old date
        await guard.sync_state()
        assert guard._halt_date is None

    @pytest.mark.asyncio
    async def test_daily_loss_within_limit_allows_open(self):
        """No halt when futures unrealized P&L is within limit."""
        inner = _mock_inner()
        inner.get_positions = AsyncMock(return_value=[
            FuturesPosition(
                symbol="101W6", quantity=1.0, avg_price=380.0,
                current_price=378.0, unrealized_pnl=-10_000.0,
                unrealized_pnl_pct=-0.5,
                market=Market.KR_FUTURES, currency="KRW",
            )
        ])
        guard = FuturesSessionGuard(inner, max_daily_loss=50_000.0)
        result = await guard.submit_order(_futures_order("101W6", "open"))
        assert result.status == "filled"

    @pytest.mark.asyncio
    async def test_daily_loss_ignores_stock_account_pnl(self):
        """Daily loss check uses futures positions only, not total account daily_pnl."""
        inner = _mock_inner()
        # Stock account shows huge loss (other simulation), but no futures positions
        inner.get_balance = AsyncMock(return_value=Balance(
            total=10_000_000, available=8_000_000, currency="KRW",
            daily_pnl=-1_000_000.0,  # massive stock loss, should be ignored
            daily_fee=0.0,
        ))
        inner.get_positions = AsyncMock(return_value=[])  # no futures positions
        guard = FuturesSessionGuard(inner, max_daily_loss=50_000.0)
        result = await guard.submit_order(_futures_order("101W6", "open"))
        assert result.status == "filled"  # not halted by stock loss

    # ── Stop-loss tests ─────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_check_stop_losses_returns_empty_when_not_configured(self):
        """check_stop_losses returns [] when stop_loss_pct is None."""
        inner = _mock_inner()
        guard = FuturesSessionGuard(inner)  # no stop_loss_pct
        result = await guard.check_stop_losses()
        assert result == []

    @pytest.mark.asyncio
    async def test_check_stop_losses_triggers_on_excess_loss(self):
        """check_stop_losses force-closes positions exceeding stop-loss threshold."""
        inner = _mock_inner()
        # Position with 3% loss (threshold is 2%)
        losing_pos = FuturesPosition(
            symbol="101W6",
            quantity=2.0,
            avg_price=380.0,
            current_price=368.6,  # ~3% loss
            unrealized_pnl=-570_000.0,
            unrealized_pnl_pct=-3.0,  # negative = loss
            market=Market.KR_FUTURES,
            currency="KRW",
        )
        inner.get_positions = AsyncMock(return_value=[losing_pos])
        guard = FuturesSessionGuard(inner, stop_loss_pct=0.02)  # 2% threshold
        guard._active_symbol = "101W6"

        closed = await guard.check_stop_losses()
        assert "101W6" in closed
        assert guard._active_symbol is None  # lock released
        inner.submit_order.assert_called_once()
        call_args = inner.submit_order.call_args[0][0]
        assert call_args.position_effect == "close"
        assert call_args.quantity == 2.0

    @pytest.mark.asyncio
    async def test_check_stop_losses_skips_profitable_positions(self):
        """Positions with positive P&L are not force-closed."""
        inner = _mock_inner()
        profitable_pos = FuturesPosition(
            symbol="101W6",
            quantity=1.0,
            avg_price=380.0,
            current_price=385.0,
            unrealized_pnl=1_250_000.0,
            unrealized_pnl_pct=1.32,  # positive = profit
            market=Market.KR_FUTURES,
            currency="KRW",
        )
        inner.get_positions = AsyncMock(return_value=[profitable_pos])
        guard = FuturesSessionGuard(inner, stop_loss_pct=0.02)

        closed = await guard.check_stop_losses()
        assert closed == []
        inner.submit_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_stop_losses_exception_returns_empty(self):
        """Exception during stop-loss check is caught — returns []."""
        inner = _mock_inner()
        inner.get_positions = AsyncMock(side_effect=Exception("network_error"))
        guard = FuturesSessionGuard(inner, stop_loss_pct=0.02)

        closed = await guard.check_stop_losses()
        assert closed == []

    # ── Position sizing tests ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_position_sizing_caps_large_order(self):
        """Order notional > 5% of capital is reduced to fit sizing limit."""
        inner = _mock_inner()
        # Capital=10M, 5%=500k, price=380, mult=250000, notional_per_contract=95M
        # Safe qty = floor(500k / (380*250000)) = 0 → clamped to 1
        inner.get_balance = AsyncMock(return_value=Balance(
            total=10_000_000, available=8_000_000, currency="KRW",
            daily_pnl=0.0, daily_fee=0.0,
        ))
        order = Order(
            symbol="101W6",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10.0,  # requests 10 contracts — way over budget
            price=380.0,
            multiplier=250_000.0,
            market=Market.KR_FUTURES,
            position_effect="open",
        )
        guard = FuturesSessionGuard(inner, position_size_pct=0.05)
        await guard.submit_order(order)
        # Should submit with reduced qty (1 contract max at this capital)
        submitted = inner.submit_order.call_args[0][0]
        assert submitted.quantity < 10.0

    @pytest.mark.asyncio
    async def test_position_sizing_allows_within_limit(self):
        """Order within position sizing limit passes unchanged."""
        inner = _mock_inner()
        inner.get_balance = AsyncMock(return_value=Balance(
            total=200_000_000, available=150_000_000, currency="KRW",
            daily_pnl=0.0, daily_fee=0.0,
        ))
        order = Order(
            symbol="105W6",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            price=380.0,
            multiplier=50_000.0,  # notional=19M, 5% of 200M=10M → 19M > 10M → capped to 1
            market=Market.KR_FUTURES,
            position_effect="open",
        )
        guard = FuturesSessionGuard(inner, position_size_pct=0.20)  # 20% → 40M limit → OK
        result = await guard.submit_order(order)
        assert result.status == "filled"
        submitted = inner.submit_order.call_args[0][0]
        assert submitted.quantity == 1.0  # unchanged

    # ── Leverage cap tests ──────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_leverage_cap_reduces_excess_qty(self):
        """Order that would exceed max_leverage is reduced in qty."""
        inner = _mock_inner()
        # available=500k, max_leverage=5x → max_notional=2.5M
        # price=380, mult=250k → notional_per=95M, requesting 5 → 475M >> 2.5M
        # safe_qty = floor(2.5M / 95M) = 0 → clamped to 1
        inner.get_balance = AsyncMock(return_value=Balance(
            total=2_000_000, available=500_000, currency="KRW",
            daily_pnl=0.0, daily_fee=0.0,
        ))
        order = Order(
            symbol="101W6",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=5.0,
            price=380.0,
            multiplier=250_000.0,
            market=Market.KR_FUTURES,
            position_effect="open",
        )
        guard = FuturesSessionGuard(inner, max_leverage=5.0)
        await guard.submit_order(order)
        submitted = inner.submit_order.call_args[0][0]
        assert submitted.quantity < 5.0

    @pytest.mark.asyncio
    async def test_leverage_cap_skips_when_no_price(self):
        """Leverage cap is skipped when order has no price (market order without price)."""
        inner = _mock_inner()
        order = Order(
            symbol="101W6",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=5.0,
            market=Market.KR_FUTURES,
            position_effect="open",
            # No price or multiplier — guard cannot compute leverage
        )
        guard = FuturesSessionGuard(inner, max_leverage=5.0)
        result = await guard.submit_order(order)
        # Should pass through (fail-open) since price/multiplier unavailable
        assert result.status == "filled"

    @pytest.mark.asyncio
    async def test_capital_limit_blocks_open_on_excess_loss(self):
        """Open is rejected when unrealized loss >= capital_limit."""
        inner = _mock_inner()
        losing_pos = _futures_position()
        losing_pos = FuturesPosition(
            symbol="101W6",
            quantity=1.0,
            avg_price=380.0,
            current_price=380.0,
            unrealized_pnl=-200_000.0,  # 200k loss
            unrealized_pnl_pct=-52.6,
            market=Market.KR_FUTURES,
            currency="KRW",
        )
        inner.get_positions = AsyncMock(return_value=[losing_pos])
        guard = FuturesSessionGuard(inner, capital_limit=100_000.0)
        result = await guard.submit_order(_futures_order("101W6", "open"))
        assert result.status == "rejected"
        assert "capital_limit_exceeded" in result.metadata["error"]

    @pytest.mark.asyncio
    async def test_max_qty_guard_with_price_and_multiplier(self):
        """Max qty guard caps contracts when price+multiplier are specified on order."""
        inner = _mock_inner()
        inner.get_positions = AsyncMock(return_value=[])
        order = Order(
            symbol="101W6",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10.0,
            price=380.0,
            multiplier=250_000.0,
            market=Market.KR_FUTURES,
            position_effect="open",
        )
        # capital_limit=100k, worst_per=9.5M → max_qty=1
        guard = FuturesSessionGuard(inner, capital_limit=100_000.0)
        await guard.submit_order(order)
        submitted = inner.submit_order.call_args[0][0]
        assert submitted.quantity == 1.0

    @pytest.mark.asyncio
    async def test_enforce_qty_by_position_closes_excess(self):
        """_enforce_qty_by_position closes excess contracts after a fill."""
        inner = _mock_inner()
        # 10 contracts held, capital=100k allows only 1 → excess=9
        large_pos = FuturesPosition(
            symbol="101W6",
            quantity=10.0,
            avg_price=380.0,
            current_price=380.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            market=Market.KR_FUTURES,
            currency="KRW",
            multiplier=250_000.0,
        )
        inner.get_positions = AsyncMock(return_value=[large_pos])
        guard = FuturesSessionGuard(inner, capital_limit=100_000.0)
        await guard._enforce_qty_by_position("101W6")
        # Should have submitted a close order for 9 excess contracts
        inner.submit_order.assert_called_once()
        close_order = inner.submit_order.call_args[0][0]
        assert close_order.position_effect == "close"
        assert close_order.quantity == 9.0

    @pytest.mark.asyncio
    async def test_enforce_qty_by_position_no_excess(self):
        """_enforce_qty_by_position does nothing when contracts are within safe limit."""
        inner = _mock_inner()
        pos = FuturesPosition(
            symbol="101W6",
            quantity=1.0,
            avg_price=380.0,
            current_price=380.0,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            market=Market.KR_FUTURES,
            currency="KRW",
            multiplier=50_000.0,  # mini → worst=1.9M per contract, 10M capital allows 5
        )
        inner.get_positions = AsyncMock(return_value=[pos])
        guard = FuturesSessionGuard(inner, capital_limit=10_000_000.0)
        await guard._enforce_qty_by_position("101W6")
        inner.submit_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_enforce_capital_limit_force_closes_when_breached(self):
        """enforce_capital_limit closes all positions when loss >= capital_limit."""
        inner = _mock_inner()
        losing_pos = FuturesPosition(
            symbol="101W6",
            quantity=3.0,
            avg_price=380.0,
            current_price=380.0,
            unrealized_pnl=-500_000.0,
            unrealized_pnl_pct=-26.3,
            market=Market.KR_FUTURES,
            currency="KRW",
        )
        inner.get_positions = AsyncMock(return_value=[losing_pos])
        guard = FuturesSessionGuard(inner, capital_limit=100_000.0)
        guard._active_symbol = "101W6"
        closed = await guard.enforce_capital_limit()
        assert closed is True
        assert guard._active_symbol is None
        inner.submit_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_enforce_capital_limit_no_positions(self):
        """enforce_capital_limit returns False when no futures positions held."""
        inner = _mock_inner()
        inner.get_positions = AsyncMock(return_value=[])
        guard = FuturesSessionGuard(inner, capital_limit=100_000.0)
        closed = await guard.enforce_capital_limit()
        assert closed is False

    @pytest.mark.asyncio
    async def test_delegate_get_order_status(self):
        """get_order_status delegates to inner adapter."""
        inner = _mock_inner()
        guard = FuturesSessionGuard(inner)
        await guard.get_order_status("OID1")
        inner.get_order_status.assert_called_once_with("OID1")

    @pytest.mark.asyncio
    async def test_delegate_cancel_order(self):
        """cancel_order delegates to inner adapter."""
        inner = _mock_inner()
        guard = FuturesSessionGuard(inner)
        await guard.cancel_order("OID1")
        inner.cancel_order.assert_called_once_with("OID1")

    @pytest.mark.asyncio
    async def test_delegate_get_fills(self):
        """get_fills delegates to inner adapter."""
        inner = _mock_inner()
        guard = FuturesSessionGuard(inner)
        await guard.get_fills()
        inner.get_fills.assert_called_once()

    @pytest.mark.asyncio
    async def test_position_sizing_exception_fails_open(self):
        """Position sizing balance check exception fails open — order is allowed."""
        inner = _mock_inner()
        inner.get_balance = AsyncMock(side_effect=Exception("balance_error"))
        order = Order(
            symbol="101W6",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10.0,
            price=380.0,
            multiplier=250_000.0,
            market=Market.KR_FUTURES,
            position_effect="open",
        )
        guard = FuturesSessionGuard(inner, position_size_pct=0.05)
        result = await guard.submit_order(order)
        # fail-open: allowed even though sizing check failed
        assert result.status == "filled"

    @pytest.mark.asyncio
    async def test_get_balance_capped_at_capital_limit(self):
        """get_balance returns capital_limit as total, not real account balance."""
        inner = _mock_inner()
        inner.get_balance = AsyncMock(return_value=Balance(
            total=50_000_000, available=15_000_000, currency="KRW"
        ))
        inner.get_positions = AsyncMock(return_value=[])
        guard = FuturesSessionGuard(inner, capital_limit=1_500_000)

        bal = await guard.get_balance()
        assert bal.total == 1_500_000
        assert bal.available == 1_500_000  # no unrealized losses

    @pytest.mark.asyncio
    async def test_get_balance_available_reduced_by_unrealized_loss(self):
        """Available capital decreases as positions incur unrealized losses."""
        from agentic_capital.ports.trading import FuturesPosition
        inner = _mock_inner()
        inner.get_balance = AsyncMock(return_value=Balance(
            total=50_000_000, available=14_000_000, currency="KRW"
        ))
        pos = MagicMock(spec=FuturesPosition)
        pos.market = Market.KR_FUTURES
        pos.unrealized_pnl = -500_000
        inner.get_positions = AsyncMock(return_value=[pos])
        guard = FuturesSessionGuard(inner, capital_limit=1_500_000)

        bal = await guard.get_balance()
        assert bal.total == 1_500_000
        assert bal.available == 1_000_000  # 1.5M - 500K loss

    @pytest.mark.asyncio
    async def test_get_balance_no_cap_when_no_capital_limit(self):
        """Without capital_limit, real balance is returned unchanged."""
        inner = _mock_inner()
        inner.get_balance = AsyncMock(return_value=Balance(
            total=50_000_000, available=15_000_000, currency="KRW"
        ))
        inner.get_positions = AsyncMock(return_value=[])
        guard = FuturesSessionGuard(inner)  # no capital_limit

        bal = await guard.get_balance()
        assert bal.total == 50_000_000
        assert bal.available == 15_000_000


# ── futures_tools ─────────────────────────────────────────────────────────────


class TestFuturesTools:
    def _build_trading(self) -> MagicMock:
        trading = MagicMock()
        trading.get_balance = AsyncMock(return_value=Balance(
            total=10_000_000, available=8_000_000, currency="KRW",
            daily_pnl=5000.0, daily_fee=200.0,
        ))
        trading.get_positions = AsyncMock(return_value=[])
        trading.get_futures_quote = AsyncMock(return_value={
            "symbol": "101W6",
            "price": 380.0,
            "open": 379.0,
            "high": 381.0,
            "low": 378.5,
            "volume": 50000,
            "change": 1.0,
            "change_pct": 0.26,
        })
        trading.submit_order = AsyncMock(return_value=OrderResult(
            order_id="OID1", symbol="101W6", side=OrderSide.BUY,
            quantity=1.0, filled_price=380.0, status="filled",
            market=Market.KR_FUTURES,
        ))
        trading.active_symbol = None
        return trading

    @pytest.mark.asyncio
    async def test_get_futures_balance(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        tools, _, _ = build_futures_tools(trading=trading, capital_limit=10_000_000)
        tool = next(t for t in tools if t.name == "get_futures_balance")
        result = await tool.ainvoke({})
        assert "tot:" in result
        assert "pnl_today:" in result
        assert "net_today:" in result

    @pytest.mark.asyncio
    async def test_get_futures_balance_no_trading(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        tools, _, _ = build_futures_tools(trading=None)
        tool = next(t for t in tools if t.name == "get_futures_balance")
        result = await tool.ainvoke({})
        assert "ERR" in result

    @pytest.mark.asyncio
    async def test_get_futures_positions_empty(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        tools, _, _ = build_futures_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_futures_positions")
        result = await tool.ainvoke({})
        assert "@fut[0]" in result

    @pytest.mark.asyncio
    async def test_get_futures_positions_with_data(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        trading.get_positions = AsyncMock(return_value=[_futures_position("101W6")])
        tools, _, _ = build_futures_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_futures_positions")
        result = await tool.ainvoke({})
        assert "101W6" in result

    @pytest.mark.asyncio
    async def test_get_futures_quote(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        tools, _, _ = build_futures_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_futures_quote")
        result = await tool.ainvoke({"symbol": "101W6"})
        assert "sym:101W6" in result
        assert "px:380" in result

    @pytest.mark.asyncio
    async def test_get_futures_quote_via_inner(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = MagicMock()
        del trading.get_futures_quote  # no direct method
        inner = MagicMock()
        inner.get_futures_quote = AsyncMock(return_value={
            "symbol": "101W6", "price": 380.0,
            "open": 379.0, "high": 381.0, "low": 378.5,
            "volume": 50000, "change": 1.0, "change_pct": 0.26,
        })
        trading._inner = inner
        tools, _, _ = build_futures_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_futures_quote")
        result = await tool.ainvoke({"symbol": "101W6"})
        assert "sym:101W6" in result

    @pytest.mark.asyncio
    async def test_get_active_symbol_locked(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        trading.active_symbol = "101W6"
        tools, _, _ = build_futures_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_active_symbol")
        result = await tool.ainvoke({})
        assert result == "locked:101W6"

    @pytest.mark.asyncio
    async def test_get_active_symbol_none(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        trading.active_symbol = None
        tools, _, _ = build_futures_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_active_symbol")
        result = await tool.ainvoke({})
        assert result == "none"

    @pytest.mark.asyncio
    async def test_submit_futures_order_success(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        tools, decisions, _ = build_futures_tools(trading=trading, agent_name="Scalper")
        tool = next(t for t in tools if t.name == "submit_futures_order")
        result = await tool.ainvoke({
            "symbol": "101W6",
            "side": "buy",
            "quantity": 1,
            "position_effect": "open",
            "reason": "momentum",
        })
        assert "oid:OID1" in result
        assert "pe:open" in result
        assert len(decisions) == 1
        assert decisions[0]["action"] == "BUY"

    @pytest.mark.asyncio
    async def test_submit_futures_order_rejected(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        trading.submit_order = AsyncMock(return_value=OrderResult(
            order_id="", symbol="101W6", side=OrderSide.BUY,
            quantity=0.0, filled_price=0.0, status="rejected",
            market=Market.KR_FUTURES,
            metadata={"error": "insufficient_margin"},
        ))
        tools, decisions, _ = build_futures_tools(trading=trading)
        tool = next(t for t in tools if t.name == "submit_futures_order")
        result = await tool.ainvoke({
            "symbol": "101W6", "side": "buy", "quantity": 1,
            "position_effect": "open",
        })
        assert "ERR:" in result
        assert len(decisions) == 0

    @pytest.mark.asyncio
    async def test_submit_futures_order_no_trading(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        tools, _, _ = build_futures_tools(trading=None)
        tool = next(t for t in tools if t.name == "submit_futures_order")
        result = await tool.ainvoke({
            "symbol": "101W6", "side": "buy", "quantity": 1,
            "position_effect": "open",
        })
        assert "ERR:no_trading" in result

    @pytest.mark.asyncio
    async def test_close_all_positions_no_positions(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        tools, decisions, _ = build_futures_tools(trading=trading)
        tool = next(t for t in tools if t.name == "close_all_positions")
        result = await tool.ainvoke({})
        assert "OK:no_positions_to_close" in result

    @pytest.mark.asyncio
    async def test_close_all_positions_with_long(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        trading.get_positions = AsyncMock(return_value=[_futures_position("101W6")])
        trading.submit_order = AsyncMock(return_value=OrderResult(
            order_id="CLOSE1", symbol="101W6", side=OrderSide.SELL,
            quantity=1.0, filled_price=381.0, status="filled",
            market=Market.KR_FUTURES,
        ))
        tools, decisions, _ = build_futures_tools(trading=trading)
        tool = next(t for t in tools if t.name == "close_all_positions")
        result = await tool.ainvoke({})
        assert "OK:closed" in result
        assert "101W6:filled" in result
        assert len(decisions) == 1

    @pytest.mark.asyncio
    async def test_close_all_positions_with_short(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        short_pos = FuturesPosition(
            symbol="101W6", quantity=1.0, avg_price=381.0,
            current_price=380.0, unrealized_pnl=250_000.0,
            unrealized_pnl_pct=0.26,
            market=Market.KR_FUTURES, currency="KRW",
            net_side="short",
        )
        trading.get_positions = AsyncMock(return_value=[short_pos])
        trading.submit_order = AsyncMock(return_value=OrderResult(
            order_id="CLOSE2", symbol="101W6", side=OrderSide.BUY,
            quantity=1.0, filled_price=380.0, status="filled",
            market=Market.KR_FUTURES,
        ))
        tools, decisions, _ = build_futures_tools(trading=trading)
        tool = next(t for t in tools if t.name == "close_all_positions")
        result = await tool.ainvoke({})
        assert "OK:closed" in result
        # Short closed with BUY
        close_call = trading.submit_order.call_args[0][0]
        assert close_call.side == OrderSide.BUY

    @pytest.mark.asyncio
    async def test_request_wakeup(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        tools, _, wakeup = build_futures_tools(trading=trading)
        tool = next(t for t in tools if t.name == "request_wakeup")
        result = await tool.ainvoke({"seconds": 60})
        assert "CYCLE_DONE" in result
        assert wakeup == [60]

    @pytest.mark.asyncio
    async def test_request_wakeup_capped_at_7200(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        tools, _, wakeup = build_futures_tools(trading=trading)
        tool = next(t for t in tools if t.name == "request_wakeup")
        await tool.ainvoke({"seconds": 99999})
        assert wakeup == [7200]

    @pytest.mark.asyncio
    async def test_request_wakeup_only_records_first(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        tools, _, wakeup = build_futures_tools(trading=trading)
        tool = next(t for t in tools if t.name == "request_wakeup")
        await tool.ainvoke({"seconds": 60})
        await tool.ainvoke({"seconds": 300})  # second call ignored
        assert len(wakeup) == 1
        assert wakeup[0] == 60

    @pytest.mark.asyncio
    async def test_get_futures_balance_exception(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        trading.get_balance = AsyncMock(side_effect=Exception("network_err"))
        tools, _, _ = build_futures_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_futures_balance")
        result = await tool.ainvoke({})
        assert "ERR:network_err" in result

    @pytest.mark.asyncio
    async def test_get_futures_positions_no_trading(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        tools, _, _ = build_futures_tools(trading=None)
        tool = next(t for t in tools if t.name == "get_futures_positions")
        result = await tool.ainvoke({})
        assert "@fut[0]" in result

    @pytest.mark.asyncio
    async def test_get_futures_quote_no_method(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = MagicMock(spec=[])  # no get_futures_quote, no _inner
        tools, _, _ = build_futures_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_futures_quote")
        result = await tool.ainvoke({"symbol": "101W6"})
        assert "ERR" in result

    @pytest.mark.asyncio
    async def test_close_all_positions_no_trading(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        tools, _, _ = build_futures_tools(trading=None)
        tool = next(t for t in tools if t.name == "close_all_positions")
        result = await tool.ainvoke({})
        assert "ERR:no_trading" in result

    @pytest.mark.asyncio
    async def test_get_futures_balance_shows_futures_pnl_only(self):
        """pnl_today must reflect futures positions only, not total account daily_pnl."""
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        # Stock account shows large loss — should be ignored
        trading.get_balance = AsyncMock(return_value=Balance(
            total=10_000_000, available=8_000_000, currency="KRW",
            daily_pnl=-1_000_000.0,  # stock loss, must not appear
            daily_fee=0.0,
        ))
        # Futures position with small unrealized gain
        trading.get_positions = AsyncMock(return_value=[_futures_position("101W6")])
        tools, _, _ = build_futures_tools(trading=trading, capital_limit=10_000_000)
        tool = next(t for t in tools if t.name == "get_futures_balance")
        result = await tool.ainvoke({})
        # pnl_today should be futures unrealized_pnl=250000, not stock -1000000
        assert "pnl_today:250000" in result
        assert "-1000000" not in result


# ── FuturesEngine (smoke tests) ───────────────────────────────────────────────


class TestFuturesEngine:
    @pytest.mark.asyncio
    async def test_engine_init(self):
        from agentic_capital.simulation.futures_engine import FuturesEngine
        engine = FuturesEngine()
        assert engine._running is False
        assert engine._cycle_count == 0
        assert engine._agent is None

    @pytest.mark.asyncio
    async def test_engine_init_adapters(self):
        from agentic_capital.simulation.futures_engine import FuturesEngine
        engine = FuturesEngine()
        with patch("agentic_capital.adapters.kis_session.KISSession"), \
             patch("agentic_capital.adapters.trading.kis.KISTradingAdapter") as mock_adapter, \
             patch("agentic_capital.adapters.trading.futures_guard.FuturesSessionGuard") as mock_guard, \
             patch("agentic_capital.infra.tracing.setup_tracing"):
            mock_inner = MagicMock()
            mock_adapter.return_value = mock_inner
            mock_guard.return_value = MagicMock()
            # Just verify no crash - adapters are imported lazily
            engine._running = True

    @pytest.mark.asyncio
    async def test_engine_init_recorder(self):
        from agentic_capital.simulation.futures_engine import FuturesEngine
        engine = FuturesEngine()
        expected_id = uuid.uuid4()
        mock_recorder_instance = MagicMock()
        mock_recorder_instance.start_simulation = AsyncMock(return_value=expected_id)
        mock_recorder_instance.commit = AsyncMock()
        with patch("agentic_capital.infra.database.async_session", return_value=MagicMock()), \
             patch("agentic_capital.simulation.recorder.SimulationRecorder",
                   return_value=mock_recorder_instance):
            result = await engine._init_recorder()
            assert engine._recorder is not None
            assert result == expected_id

    @pytest.mark.asyncio
    async def test_engine_create_agent(self):
        from agentic_capital.simulation.futures_engine import FuturesEngine
        engine = FuturesEngine()
        sim_id = uuid.uuid4()
        with patch("agentic_capital.simulation.futures_engine.create_random_personality") as mock_p, \
             patch("agentic_capital.simulation.futures_engine.create_agent_profile") as mock_profile:
            mock_p.return_value = MagicMock()
            mock_profile.return_value = MagicMock()
            engine._create_agent(sim_id)
            assert engine._agent is not None
            assert mock_profile.call_args[1]["name"] == "Scalper-Alpha"

    @pytest.mark.asyncio
    async def test_engine_start_runs_one_cycle_then_stops(self):
        """start() loops while _running; we stop after one cycle."""
        from agentic_capital.simulation.futures_engine import FuturesEngine
        engine = FuturesEngine()

        call_count = 0

        async def fake_run_cycle():
            nonlocal call_count
            call_count += 1
            engine._running = False  # stop after first cycle
            return 0.0  # no sleep

        engine._running = True
        engine._trading = MagicMock()
        engine._trading.sync_state = AsyncMock()
        engine._recorder = MagicMock()
        engine._agent = MagicMock()
        engine._agent.name = "Scalper-Alpha"
        engine._agent.agent_id = uuid.uuid4()

        with patch.object(engine, "_init_adapters"), \
             patch.object(engine, "_init_recorder"), \
             patch.object(engine, "_create_agent"), \
             patch.object(engine, "_run_cycle", side_effect=fake_run_cycle), \
             patch("agentic_capital.simulation.futures_engine.uuid") as mock_uuid:
            mock_uuid.uuid4.return_value = uuid.uuid4()
            await engine.start()

        assert call_count == 1

    def _make_engine_with_mocks(self):
        """Build a FuturesEngine with all external deps mocked."""
        from agentic_capital.simulation.futures_engine import FuturesEngine
        engine = FuturesEngine()

        # Mock trading (guard)
        trading = MagicMock()
        trading.active_symbol = None
        trading.sync_state = AsyncMock()
        trading.enforce_capital_limit = AsyncMock(return_value=False)
        trading.check_stop_losses = AsyncMock(return_value=[])
        engine._trading = trading

        # Mock recorder
        recorder = MagicMock()
        recorder.record_agent_cycle = AsyncMock()
        recorder.commit = AsyncMock()
        engine._recorder = recorder

        # Mock agent
        agent = MagicMock()
        agent.agent_id = uuid.uuid4()
        agent.name = "Scalper-Alpha"
        agent.profile.philosophy = "scalp hard"
        agent.personality = MagicMock(
            openness=0.5, conscientiousness=0.5, extraversion=0.5,
            agreeableness=0.5, neuroticism=0.3, honesty_humility=0.6,
            loss_aversion=0.4, risk_aversion_gains=0.4,
            risk_aversion_losses=0.5, probability_weighting=0.6,
        )
        agent.emotion = MagicMock(
            valence=0.5, arousal=0.5, dominance=0.5, stress=0.2, confidence=0.7,
        )
        engine._agent = agent
        engine._running = True
        engine._cycle_count = 0

        return engine

    @pytest.mark.asyncio
    async def test_run_cycle_returns_wakeup_from_sink(self):
        engine = self._make_engine_with_mocks()

        # Patch build_futures_tools to return a wakeup sink with a value
        mock_tools = []
        decisions_sink = []
        wakeup_sink = [120]

        with patch("agentic_capital.core.tools.futures_tools.build_futures_tools",
                   return_value=(mock_tools, decisions_sink, wakeup_sink)), \
             patch("agentic_capital.simulation.futures_engine.get_open_markets",
                   return_value=["KRX"]), \
             patch("langchain_google_genai.ChatGoogleGenerativeAI"), \
             patch("langgraph.prebuilt.create_react_agent") as mock_create_agent:
            mock_react = AsyncMock()
            mock_react.ainvoke = AsyncMock(return_value={"messages": []})
            mock_create_agent.return_value = mock_react

            next_secs = await engine._run_cycle()
            assert next_secs == 120.0

    @pytest.mark.asyncio
    async def test_run_cycle_default_wakeup_on_empty_sink(self):
        """When market open but agent doesn't call request_wakeup, use default 60s."""
        engine = self._make_engine_with_mocks()
        engine._recorder = None

        mock_tools = []
        decisions_sink = []
        wakeup_sink = []  # empty

        with patch("agentic_capital.core.tools.futures_tools.build_futures_tools",
                   return_value=(mock_tools, decisions_sink, wakeup_sink)), \
             patch("agentic_capital.simulation.futures_engine.get_open_markets",
                   return_value=["KRX"]), \
             patch("langchain_google_genai.ChatGoogleGenerativeAI"), \
             patch("langgraph.prebuilt.create_react_agent") as mock_create_agent:
            mock_react = MagicMock()
            mock_react.ainvoke = AsyncMock(return_value={"messages": []})
            mock_create_agent.return_value = mock_react

            next_secs = await engine._run_cycle()
            assert next_secs == 60.0  # _DEFAULT_CYCLE_SECONDS

    @pytest.mark.asyncio
    async def test_run_cycle_skips_ai_when_market_closed(self):
        """When futures market is closed, skip AI entirely and return sleep time."""
        engine = self._make_engine_with_mocks()
        engine._recorder = None

        with patch("agentic_capital.simulation.futures_engine.get_open_markets",
                   return_value=[]), \
             patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_llm:
            next_secs = await engine._run_cycle()
            # Should sleep (60 <= secs <= 3600), never call LLM
            assert 60.0 <= next_secs <= 3600.0
            mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_cycle_handles_exception(self):
        engine = self._make_engine_with_mocks()
        engine._recorder = None

        with patch("agentic_capital.core.tools.futures_tools.build_futures_tools",
                   return_value=([], [], [])), \
             patch("agentic_capital.simulation.futures_engine.get_open_markets",
                   return_value=["KRX"]), \
             patch("langchain_google_genai.ChatGoogleGenerativeAI"), \
             patch("langgraph.prebuilt.create_react_agent") as mock_create_agent:
            mock_react = MagicMock()
            mock_react.ainvoke = AsyncMock(side_effect=Exception("llm_error"))
            mock_create_agent.return_value = mock_react

            # Should not raise — exception is caught inside _run_cycle
            next_secs = await engine._run_cycle()
            assert next_secs == 60.0

    @pytest.mark.asyncio
    async def test_run_cycle_recorder_exception_logged(self):
        """Recorder failure is caught and logged, not propagated."""
        engine = self._make_engine_with_mocks()
        engine._recorder.record_agent_cycle = AsyncMock(side_effect=Exception("db_error"))
        decisions_sink = [{"type": "trade"}]
        wakeup_sink = [60]

        with patch("agentic_capital.core.tools.futures_tools.build_futures_tools",
                   return_value=([], decisions_sink, wakeup_sink)), \
             patch("agentic_capital.simulation.futures_engine.get_open_markets",
                   return_value=["KRX"]), \
             patch("langchain_google_genai.ChatGoogleGenerativeAI"), \
             patch("langgraph.prebuilt.create_react_agent") as mock_create_agent, \
             patch("agentic_capital.graph.nodes.record_cycle", new_callable=AsyncMock), \
             patch("agentic_capital.graph.workflow._extract_tool_sequence", return_value=[]), \
             patch("agentic_capital.graph.workflow._extract_llm_reasoning", return_value=""):
            mock_react = MagicMock()
            mock_react.ainvoke = AsyncMock(return_value={"messages": []})
            mock_create_agent.return_value = mock_react

            # Should not raise despite recorder failure
            next_secs = await engine._run_cycle()
            assert next_secs == 60.0

    @pytest.mark.asyncio
    async def test_start_handles_cycle_exception_and_retries(self):
        """start() catches cycle exceptions and sleeps 30s before retrying."""
        from agentic_capital.simulation.futures_engine import FuturesEngine
        engine = FuturesEngine()

        call_count = 0

        async def fake_run_cycle():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("transient_error")
            engine._running = False
            return 0.0

        engine._trading = MagicMock()
        engine._trading.sync_state = AsyncMock()
        engine._recorder = MagicMock()
        engine._agent = MagicMock()
        engine._agent.name = "Scalper-Alpha"
        engine._agent.agent_id = uuid.uuid4()

        with patch.object(engine, "_init_adapters"), \
             patch.object(engine, "_init_recorder"), \
             patch.object(engine, "_create_agent"), \
             patch.object(engine, "_run_cycle", side_effect=fake_run_cycle), \
             patch("agentic_capital.simulation.futures_engine.asyncio.sleep", new_callable=AsyncMock), \
             patch("agentic_capital.simulation.futures_engine.uuid") as mock_uuid:
            mock_uuid.uuid4.return_value = uuid.uuid4()
            await engine.start()

        assert call_count == 2  # first raised, second stopped the loop

    @pytest.mark.asyncio
    async def test_session_end_auto_close_skips_ai(self):
        """When within 10 min of session end and position open, AI is skipped and positions closed."""
        engine = self._make_engine_with_mocks()
        engine._recorder = None
        engine._trading.active_symbol = "101W6"

        with patch("agentic_capital.simulation.futures_engine.get_open_markets",
                   return_value=["KRX"]), \
             patch.object(engine, "_minutes_until_session_end", return_value=5.0), \
             patch.object(engine, "_close_all_now", new_callable=AsyncMock) as mock_close, \
             patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_llm:
            next_secs = await engine._run_cycle()
            mock_close.assert_called_once_with(reason="session_end")
            mock_llm.assert_not_called()
            assert next_secs >= 300

    @pytest.mark.asyncio
    async def test_session_end_no_close_when_flat(self):
        """Session-end auto-close skipped when no active position."""
        engine = self._make_engine_with_mocks()
        engine._recorder = None
        engine._trading.active_symbol = None  # flat

        with patch("agentic_capital.simulation.futures_engine.get_open_markets",
                   return_value=["KRX"]), \
             patch.object(engine, "_minutes_until_session_end", return_value=5.0), \
             patch.object(engine, "_close_all_now", new_callable=AsyncMock) as mock_close, \
             patch("agentic_capital.core.tools.futures_tools.build_futures_tools",
                   return_value=([], [], [60])), \
             patch("langchain_google_genai.ChatGoogleGenerativeAI"), \
             patch("langgraph.prebuilt.create_react_agent") as mock_create_agent:
            mock_react = MagicMock()
            mock_react.ainvoke = AsyncMock(return_value={"messages": []})
            mock_create_agent.return_value = mock_react
            await engine._run_cycle()
            mock_close.assert_not_called()  # no position to close

    @pytest.mark.asyncio
    async def test_run_cycle_records_to_db(self):
        engine = self._make_engine_with_mocks()
        decisions_sink = [{"type": "trade"}]
        wakeup_sink = [60]

        with patch("agentic_capital.core.tools.futures_tools.build_futures_tools",
                   return_value=([], decisions_sink, wakeup_sink)), \
             patch("agentic_capital.simulation.futures_engine.get_open_markets",
                   return_value=["KRX"]), \
             patch("langchain_google_genai.ChatGoogleGenerativeAI"), \
             patch("langgraph.prebuilt.create_react_agent") as mock_create_agent, \
             patch("agentic_capital.graph.nodes.record_cycle", new_callable=AsyncMock), \
             patch("agentic_capital.graph.workflow._extract_tool_sequence", return_value=[]), \
             patch("agentic_capital.graph.workflow._extract_llm_reasoning", return_value=""):
            mock_react = MagicMock()
            mock_react.ainvoke = AsyncMock(return_value={"messages": []})
            mock_create_agent.return_value = mock_react

            await engine._run_cycle()
            engine._recorder.record_agent_cycle.assert_called_once()
            engine._recorder.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_deadman_switch_triggers_after_max_errors(self):
        """After deadman_max_errors consecutive failures, all positions are closed and cooldown starts."""
        from agentic_capital.simulation.futures_engine import FuturesEngine
        engine = FuturesEngine()
        engine._deadman_max_errors = 3
        engine._deadman_cooldown_secs = 1
        engine._consecutive_errors = 0

        call_count = 0

        async def fake_run_cycle():
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise RuntimeError("api_error")
            engine._running = False
            return 0.0

        engine._trading = MagicMock()
        engine._trading.sync_state = AsyncMock()
        engine._recorder = None
        engine._agent = MagicMock()
        engine._agent.name = "Scalper-Alpha"
        engine._agent.agent_id = uuid.uuid4()

        close_all_calls = []

        async def fake_close_all(reason=""):
            close_all_calls.append(reason)

        with patch.object(engine, "_init_adapters"), \
             patch.object(engine, "_init_recorder"), \
             patch.object(engine, "_create_agent"), \
             patch.object(engine, "_run_cycle", side_effect=fake_run_cycle), \
             patch.object(engine, "_close_all_now", side_effect=fake_close_all), \
             patch("agentic_capital.simulation.futures_engine.asyncio.sleep", new_callable=AsyncMock), \
             patch("agentic_capital.simulation.futures_engine.uuid") as mock_uuid:
            mock_uuid.uuid4.return_value = uuid.uuid4()
            await engine.start()

        # Deadman should have triggered once (3 errors → trigger), then 4th call stopped loop
        assert "deadman_switch" in close_all_calls

    @pytest.mark.asyncio
    async def test_deadman_resets_counter_after_trigger(self):
        """consecutive_errors is reset to 0 after deadman triggers."""
        from agentic_capital.simulation.futures_engine import FuturesEngine
        engine = FuturesEngine()
        engine._deadman_max_errors = 2
        engine._deadman_cooldown_secs = 0
        engine._consecutive_errors = 0

        call_count = 0

        async def fake_run_cycle():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError("api_error")
            engine._running = False
            return 0.0

        engine._trading = MagicMock()
        engine._trading.sync_state = AsyncMock()
        engine._recorder = None
        engine._agent = MagicMock()
        engine._agent.agent_id = uuid.uuid4()

        with patch.object(engine, "_init_adapters"), \
             patch.object(engine, "_init_recorder"), \
             patch.object(engine, "_create_agent"), \
             patch.object(engine, "_run_cycle", side_effect=fake_run_cycle), \
             patch.object(engine, "_close_all_now", new_callable=AsyncMock), \
             patch("agentic_capital.simulation.futures_engine.asyncio.sleep", new_callable=AsyncMock), \
             patch("agentic_capital.simulation.futures_engine.uuid") as mock_uuid:
            mock_uuid.uuid4.return_value = uuid.uuid4()
            await engine.start()

        assert engine._consecutive_errors == 0  # reset after deadman triggered

    @pytest.mark.asyncio
    async def test_volatility_filter_skips_cycle_on_high_volatility(self):
        """_run_cycle returns early and closes positions when KOSPI200 moves > threshold."""
        engine = self._make_engine_with_mocks()
        engine._recorder = None
        engine._volatility_threshold_pct = 1.5
        engine._trading.active_symbol = "101W6"

        volatile_data = {"price": 390.0, "open": 380.0, "change_pct": 2.6}

        with patch("agentic_capital.simulation.futures_engine.get_open_markets",
                   return_value=["KRX"]), \
             patch("agentic_capital.adapters.trading.kis._fetch_yfinance_kospi200",
                   new=AsyncMock(return_value=volatile_data)), \
             patch.object(engine, "_close_all_now", new_callable=AsyncMock) as mock_close, \
             patch.object(engine, "_minutes_until_session_end", return_value=999.0), \
             patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_llm:
            next_secs = await engine._run_cycle()
            mock_close.assert_called_once_with(reason="volatility_filter")
            mock_llm.assert_not_called()
            assert next_secs == 120.0  # 2x default (60*2)

    @pytest.mark.asyncio
    async def test_volatility_filter_proceeds_when_calm(self):
        """When volatility is below threshold, AI cycle proceeds normally."""
        engine = self._make_engine_with_mocks()
        engine._recorder = None
        engine._volatility_threshold_pct = 2.0

        calm_data = {"price": 381.0, "open": 380.0, "change_pct": 0.26}

        with patch("agentic_capital.simulation.futures_engine.get_open_markets",
                   return_value=["KRX"]), \
             patch("agentic_capital.adapters.trading.kis._fetch_yfinance_kospi200",
                   new=AsyncMock(return_value=calm_data)), \
             patch("agentic_capital.core.tools.futures_tools.build_futures_tools",
                   return_value=([], [], [60])), \
             patch("langchain_google_genai.ChatGoogleGenerativeAI"), \
             patch("langgraph.prebuilt.create_react_agent") as mock_create_agent:
            mock_react = MagicMock()
            mock_react.ainvoke = AsyncMock(return_value={"messages": []})
            mock_create_agent.return_value = mock_react
            next_secs = await engine._run_cycle()
            # AI was invoked — normal cycle
            mock_create_agent.assert_called_once()
            assert next_secs == 60.0


# ── FuturesVirtualAdapter tests ───────────────────────────────────────────────


class TestFuturesVirtualAdapter:
    """Tests for FuturesVirtualAdapter (local futures simulation)."""

    def _make_adapter(self, price: float = 380.0, capital: float = 50_000_000.0):
        from agentic_capital.adapters.trading.futures_virtual import FuturesVirtualAdapter
        inner = _mock_inner()
        inner.get_positions = AsyncMock(return_value=[])  # no real stock positions
        adapter = FuturesVirtualAdapter(inner, initial_capital=capital)
        return adapter, price

    def _patch_price(self, price: float):
        from unittest.mock import patch
        return patch(
            "agentic_capital.adapters.trading.kis._fetch_yfinance_kospi200",
            new=AsyncMock(return_value={"price": price, "open": price, "high": price,
                                        "low": price, "volume": 1000, "change": 0.0, "change_pct": 0.0}),
        )

    @pytest.mark.asyncio
    async def test_initial_balance_equals_capital(self):
        adapter, price = self._make_adapter(380.0, capital=50_000_000.0)
        with self._patch_price(price):
            bal = await adapter.get_balance()
        assert bal.total == 50_000_000.0
        assert bal.available == 50_000_000.0
        assert bal.currency == "KRW"

    @pytest.mark.asyncio
    async def test_open_position_fills_virtually(self):
        adapter, price = self._make_adapter(380.0)
        order = Order(
            symbol="101F6", side=OrderSide.BUY, quantity=1.0,
            market=Market.KR_FUTURES, position_effect="open",
        )
        with self._patch_price(price):
            result = await adapter.submit_order(order)
        assert result.status == "filled"
        assert result.filled_price == 380.0
        assert result.symbol == "101F6"

    @pytest.mark.asyncio
    async def test_position_unrealized_pnl_updated(self):
        adapter, _ = self._make_adapter(380.0)
        order = Order(
            symbol="101F6", side=OrderSide.BUY, quantity=1.0,
            market=Market.KR_FUTURES, position_effect="open", multiplier=250_000.0,
        )
        with self._patch_price(380.0):
            await adapter.submit_order(order)
        # Price moves up 1 point
        with self._patch_price(381.0):
            positions = await adapter.get_positions()
        fut_pos = [p for p in positions if p.market == Market.KR_FUTURES]
        assert len(fut_pos) == 1
        assert fut_pos[0].unrealized_pnl == pytest.approx(250_000.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_close_position_removes_from_positions(self):
        adapter, price = self._make_adapter(380.0)
        open_order = Order(
            symbol="101F6", side=OrderSide.BUY, quantity=1.0,
            market=Market.KR_FUTURES, position_effect="open",
        )
        close_order = Order(
            symbol="101F6", side=OrderSide.SELL, quantity=1.0,
            market=Market.KR_FUTURES, position_effect="close",
        )
        with self._patch_price(price):
            await adapter.submit_order(open_order)
            result = await adapter.submit_order(close_order)
        assert result.status == "filled"
        with self._patch_price(price):
            positions = await adapter.get_positions()
        assert not any(p.market == Market.KR_FUTURES for p in positions)

    @pytest.mark.asyncio
    async def test_rejected_when_insufficient_margin(self):
        # Capital of 100 KRW — clearly not enough for any futures margin
        adapter, _ = self._make_adapter(380.0, capital=100.0)
        order = Order(
            symbol="101F6", side=OrderSide.BUY, quantity=1.0,
            market=Market.KR_FUTURES, position_effect="open",
        )
        with self._patch_price(380.0):
            result = await adapter.submit_order(order)
        assert result.status == "rejected"

    @pytest.mark.asyncio
    async def test_non_futures_order_delegated_to_inner(self):
        adapter, price = self._make_adapter(380.0)
        stock_order = Order(
            symbol="005930", side=OrderSide.BUY, quantity=1.0,
            market=Market.KR_STOCK,
        )
        with self._patch_price(price):
            result = await adapter.submit_order(stock_order)
        # Should be handled by inner (mocked to return OID1/filled)
        assert result.order_id == "OID1"

    @pytest.mark.asyncio
    async def test_invalid_symbol_rejected(self):
        """Hallucinated symbols like 101RC000 are rejected with error."""
        adapter, price = self._make_adapter(380.0)
        bad_order = Order(
            symbol="101RC000", side=OrderSide.BUY, quantity=1.0,
            market=Market.KR_FUTURES, position_effect="open",
        )
        with self._patch_price(price):
            result = await adapter.submit_order(bad_order)
        assert result.status == "rejected"
        assert "invalid_symbol" in result.metadata.get("error", "")

    def test_valid_symbol_patterns(self):
        from agentic_capital.adapters.trading.futures_virtual import FuturesVirtualAdapter
        assert FuturesVirtualAdapter._is_valid_kospi200_symbol("101F6")
        assert FuturesVirtualAdapter._is_valid_kospi200_symbol("105C6")
        assert FuturesVirtualAdapter._is_valid_kospi200_symbol("101I7")
        assert not FuturesVirtualAdapter._is_valid_kospi200_symbol("101RC000")
        assert not FuturesVirtualAdapter._is_valid_kospi200_symbol("KOSPI200")
        assert not FuturesVirtualAdapter._is_valid_kospi200_symbol("005930")
