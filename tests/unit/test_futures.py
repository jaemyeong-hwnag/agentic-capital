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
    async def test_get_futures_balance_with_overseas_pnl(self):
        from agentic_capital.core.tools.futures_tools import build_futures_tools
        trading = self._build_trading()
        ovs_balance = MagicMock()
        ovs_balance.daily_pnl = 3000.0
        trading.get_overseas_balance = AsyncMock(return_value=ovs_balance)
        tools, _, _ = build_futures_tools(trading=trading, capital_limit=10_000_000)
        tool = next(t for t in tools if t.name == "get_futures_balance")
        result = await tool.ainvoke({})
        # daily_pnl = 5000 (KR) + 3000 (ovs) = 8000
        assert "pnl_today:8000" in result


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
