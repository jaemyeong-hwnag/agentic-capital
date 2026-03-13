"""Tests for paper trading adapter."""

import pytest

from agentic_capital.adapters.trading.paper import PaperTradingAdapter
from agentic_capital.ports.trading import Order, OrderSide


@pytest.fixture
def adapter() -> PaperTradingAdapter:
    return PaperTradingAdapter(initial_balance=100_000.0)


class TestPaperTrading:
    @pytest.mark.asyncio
    async def test_initial_balance(self, adapter: PaperTradingAdapter) -> None:
        balance = await adapter.get_balance()
        assert balance.total == 100_000.0
        assert balance.available == 100_000.0

    @pytest.mark.asyncio
    async def test_buy_order(self, adapter: PaperTradingAdapter) -> None:
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, price=150.0)
        result = await adapter.submit_order(order)
        assert result.status == "filled"
        assert result.filled_price == 150.0

        balance = await adapter.get_balance()
        assert balance.available == pytest.approx(100_000.0 - 1500.0)

    @pytest.mark.asyncio
    async def test_buy_then_sell(self, adapter: PaperTradingAdapter) -> None:
        buy = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, price=150.0)
        await adapter.submit_order(buy)

        sell = Order(symbol="AAPL", side=OrderSide.SELL, quantity=10, price=160.0)
        result = await adapter.submit_order(sell)
        assert result.status == "filled"

        balance = await adapter.get_balance()
        # Bought at 150, sold at 160 → profit $100
        assert balance.available == pytest.approx(100_000.0 + 100.0)

    @pytest.mark.asyncio
    async def test_insufficient_funds_rejected(self, adapter: PaperTradingAdapter) -> None:
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=1000, price=150.0)
        result = await adapter.submit_order(order)
        assert result.status == "rejected"

    @pytest.mark.asyncio
    async def test_sell_without_position_rejected(self, adapter: PaperTradingAdapter) -> None:
        order = Order(symbol="AAPL", side=OrderSide.SELL, quantity=10, price=150.0)
        result = await adapter.submit_order(order)
        assert result.status == "rejected"

    @pytest.mark.asyncio
    async def test_positions_tracked(self, adapter: PaperTradingAdapter) -> None:
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, price=150.0)
        await adapter.submit_order(order)

        positions = await adapter.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == 10

    @pytest.mark.asyncio
    async def test_partial_sell(self, adapter: PaperTradingAdapter) -> None:
        buy = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, price=150.0)
        await adapter.submit_order(buy)

        sell = Order(symbol="AAPL", side=OrderSide.SELL, quantity=5, price=160.0)
        await adapter.submit_order(sell)

        positions = await adapter.get_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 5

    @pytest.mark.asyncio
    async def test_order_status(self, adapter: PaperTradingAdapter) -> None:
        order = Order(symbol="AAPL", side=OrderSide.BUY, quantity=10, price=150.0)
        result = await adapter.submit_order(order)

        status = await adapter.get_order_status(result.order_id)
        assert status.status == "filled"

    @pytest.mark.asyncio
    async def test_order_status_not_found(self, adapter: PaperTradingAdapter) -> None:
        status = await adapter.get_order_status("nonexistent")
        assert status.status == "not_found"
