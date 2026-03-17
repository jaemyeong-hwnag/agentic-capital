"""Unit tests for build_agent_tools()."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_capital.core.tools.data_query import build_agent_tools


def _make_trading():
    trading = MagicMock()
    trading.get_balance = AsyncMock(
        return_value=MagicMock(total=10_000_000, available=8_000_000, currency="KRW")
    )
    trading.get_positions = AsyncMock(return_value=[
        MagicMock(
            symbol="005930", quantity=100, avg_price=70000,
            current_price=72000, unrealized_pnl=200000, unrealized_pnl_pct=2.86,
            market="kr_stock", currency="KRW",
        ),
    ])
    trading.submit_order = AsyncMock(
        return_value=MagicMock(
            order_id="ORDER123", symbol="005930", side="buy",
            quantity=10, filled_price=70000.0, status="submitted", market="kr_stock",
        )
    )
    trading.cancel_order = AsyncMock(return_value=True)
    trading.get_fills = AsyncMock(return_value=[
        MagicMock(order_id="O1", symbol="005930", side="buy", quantity=10, filled_price=70000, status="filled"),
    ])
    return trading


class TestBuildAgentTools:
    """Test build_agent_tools() returns correct tools and they work."""

    def test_returns_tools_and_sinks(self):
        tools, decisions, messages, wakeups = build_agent_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
        assert isinstance(decisions, list)
        assert isinstance(messages, list)
        assert isinstance(wakeups, list)

    def test_tool_names(self):
        tools, _, _, _ = build_agent_tools()
        names = {t.name for t in tools}
        assert "get_balance" in names
        assert "get_positions" in names
        assert "get_fills" in names
        assert "submit_order" in names
        assert "cancel_order" in names
        assert "save_memory" in names
        assert "search_memory" in names
        assert "send_message" in names
        assert "request_wakeup" in names
        assert "get_quote" in names
        assert "get_ohlcv" in names
        assert "get_market_status" in names
        assert "create_tool" in names
        assert "hire_agent" in names
        assert "fire_agent" in names
        assert "create_role" in names

    @pytest.mark.asyncio
    async def test_get_balance_tool(self):
        trading = _make_trading()
        tools, _, _, _ = build_agent_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_balance")
        result = await tool.coroutine()
        assert "tot:10000000" in result
        assert "avl:8000000" in result
        assert "ccy:KRW" in result

    @pytest.mark.asyncio
    async def test_get_balance_capped_by_capital_limit(self):
        trading = _make_trading()  # total=10M, available=8M
        # Capital limit lower than KIS balance → use limit
        tools, _, _, _ = build_agent_tools(trading=trading, capital_limit=5_000_000)
        tool = next(t for t in tools if t.name == "get_balance")
        result = await tool.coroutine()
        assert "tot:5000000" in result
        assert "avl:5000000" in result  # available also capped

    @pytest.mark.asyncio
    async def test_get_balance_kis_lower_than_limit(self):
        trading = _make_trading()  # total=10M, available=8M
        # Capital limit higher than KIS balance → use KIS
        tools, _, _, _ = build_agent_tools(trading=trading, capital_limit=15_000_000)
        tool = next(t for t in tools if t.name == "get_balance")
        result = await tool.coroutine()
        assert "tot:10000000" in result
        assert "avl:8000000" in result

    @pytest.mark.asyncio
    async def test_get_balance_no_trading(self):
        tools, _, _, _ = build_agent_tools()
        tool = next(t for t in tools if t.name == "get_balance")
        result = await tool.coroutine()
        assert result.startswith("ERR:")

    @pytest.mark.asyncio
    async def test_get_positions_tool(self):
        trading = _make_trading()
        tools, _, _, _ = build_agent_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_positions")
        result = await tool.coroutine()
        assert "@pos[1]" in result
        assert "005930" in result

    @pytest.mark.asyncio
    async def test_get_fills_tool(self):
        trading = _make_trading()
        tools, _, _, _ = build_agent_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_fills")
        result = await tool.coroutine()
        assert "@fills[1]" in result
        assert "O1" in result
        assert "005930" in result

    @pytest.mark.asyncio
    async def test_submit_order_tool_records_decision(self):
        trading = _make_trading()
        tools, decisions, _, _ = build_agent_tools(trading=trading, agent_name="Trader-1")
        tool = next(t for t in tools if t.name == "submit_order")
        result = await tool.coroutine(
            symbol="005930", side="buy", quantity=10, price=70000.0, market="kr_stock"
        )
        assert "submitted" in result
        assert "005930" in result
        assert len(decisions) == 1
        assert decisions[0]["symbol"] == "005930"
        assert decisions[0]["action"] == "BUY"

    @pytest.mark.asyncio
    async def test_submit_order_no_trading(self):
        tools, _, _, _ = build_agent_tools()
        tool = next(t for t in tools if t.name == "submit_order")
        result = await tool.coroutine(symbol="005930", side="buy", quantity=10, market="kr_stock")
        assert result.startswith("ERR:")

    @pytest.mark.asyncio
    async def test_cancel_order_tool(self):
        trading = _make_trading()
        tools, _, _, _ = build_agent_tools(trading=trading)
        tool = next(t for t in tools if t.name == "cancel_order")
        result = await tool.coroutine(order_id="ORDER123", market="kr_stock")
        assert "cancelled:True" in result
        assert "ORDER123" in result

    @pytest.mark.asyncio
    async def test_save_and_search_memory(self):
        memory = {}
        tools, _, _, _ = build_agent_tools(agent_memory=memory)

        save_tool = next(t for t in tools if t.name == "save_memory")
        search_tool = next(t for t in tools if t.name == "search_memory")

        save_result = await save_tool.coroutine(content="Samsung Electronics up 5%", keywords=["005930", "bullish"])
        assert "saved:1" in save_result

        results = await search_tool.coroutine(query="bullish")
        assert "Samsung" in results
        assert "005930" in results

    @pytest.mark.asyncio
    async def test_search_memory_no_match(self):
        memory = {}
        tools, _, _, _ = build_agent_tools(agent_memory=memory)
        search_tool = next(t for t in tools if t.name == "search_memory")
        results = await search_tool.coroutine(query="nonexistent")
        assert results == "[]"

    @pytest.mark.asyncio
    async def test_send_message_tool(self):
        tools, _, messages, _ = build_agent_tools(agent_name="CEO-Alpha")
        tool = next(t for t in tools if t.name == "send_message")
        result = await tool.coroutine(
            to_agent="Trader-Gamma",
            type="INSTR",
            content="action:buy,sym:005930",
        )
        assert result == "sent:1"
        assert len(messages) == 1
        assert messages[0]["to"] == "Trader-Gamma"
        assert messages[0]["from"] == "CEO-Alpha"
        assert "wire" in messages[0]
        assert "INSTR|CEO-Alpha|Trader-Gamma" in messages[0]["wire"]

    @pytest.mark.asyncio
    async def test_request_wakeup_records_delay(self):
        tools, _, _, wakeups = build_agent_tools(agent_name="CEO-Alpha")
        tool = next(t for t in tools if t.name == "request_wakeup")
        result = await tool.coroutine(seconds=3600)
        assert "3600" in result
        assert wakeups == [3600]

    @pytest.mark.asyncio
    async def test_request_wakeup_zero_immediate(self):
        tools, _, _, wakeups = build_agent_tools()
        tool = next(t for t in tools if t.name == "request_wakeup")
        await tool.coroutine(seconds=0)
        assert wakeups == [0]

    @pytest.mark.asyncio
    async def test_request_wakeup_negative_clamped(self):
        tools, _, _, wakeups = build_agent_tools()
        tool = next(t for t in tools if t.name == "request_wakeup")
        await tool.coroutine(seconds=-100)
        assert wakeups == [0]

    @pytest.mark.asyncio
    async def test_get_market_status_tool(self):
        from unittest.mock import patch, MagicMock
        tools, _, _, _ = build_agent_tools()
        tool = next(t for t in tools if t.name == "get_market_status")

        mock_info = {"marketState": "POSTPOST"}
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info

        with patch("yfinance.Ticker", return_value=mock_ticker):
            result = await tool.coroutine()

        assert "KRX" in result
        assert "NASDAQ" in result
        assert "NYSE" in result
        assert "POSTPOST" in result

    @pytest.mark.asyncio
    async def test_submit_order_blocked_when_exceeds_capital(self):
        trading = _make_trading()  # available=8M
        tools, _, _, _ = build_agent_tools(trading=trading, capital_limit=5_000_000)
        tool = next(t for t in tools if t.name == "submit_order")
        # 100 shares × 70,000 = 7,000,000 > capital_limit 5,000,000
        result = await tool.coroutine(
            symbol="005930", side="buy", quantity=100, price=70000.0, market="kr_stock"
        )
        assert result.startswith("ERR:insufficient_capital")
        assert "need:7000000" in result
        assert "avl:5000000" in result
        assert "max_qty:71" in result

    @pytest.mark.asyncio
    async def test_submit_order_allowed_within_capital(self):
        trading = _make_trading()  # available=8M
        tools, _, _, _ = build_agent_tools(trading=trading, capital_limit=10_000_000)
        tool = next(t for t in tools if t.name == "submit_order")
        # 10 shares × 70,000 = 700,000 < capital_limit 10,000,000
        result = await tool.coroutine(
            symbol="005930", side="buy", quantity=10, price=70000.0, market="kr_stock"
        )
        assert "submitted" in result

    @pytest.mark.asyncio
    async def test_submit_order_sell_not_blocked_by_capital(self):
        trading = _make_trading()
        trading.submit_order.return_value.side = "sell"
        tools, _, _, _ = build_agent_tools(trading=trading, capital_limit=100)  # tiny limit
        tool = next(t for t in tools if t.name == "submit_order")
        # SELL should never be blocked by capital check
        result = await tool.coroutine(
            symbol="005930", side="sell", quantity=10, price=70000.0, market="kr_stock"
        )
        assert not result.startswith("ERR:insufficient_capital")

    @pytest.mark.asyncio
    async def test_set_position_policy_tool(self):
        tools, _, _, _ = build_agent_tools(agent_name="Risk-Alpha")
        set_tool = next(t for t in tools if t.name == "set_position_policy")
        get_tool = next(t for t in tools if t.name == "get_position_policy")

        result = await set_tool.coroutine(max_per_trade_pct=0.25, max_per_symbol_pct=0.5)
        assert "max_per_trade:25%" in result
        assert "max_per_symbol:50%" in result
        assert "effective:immediately" in result

        policy = await get_tool.coroutine()
        assert "max_per_trade:25%" in policy
        assert "Risk-Alpha" in policy

    @pytest.mark.asyncio
    async def test_position_policy_blocks_oversized_order(self):
        from agentic_capital.core.tools import data_query as dq
        # Reset policy first
        dq._POSITION_POLICY["max_per_trade_pct"] = 0.20
        dq._POSITION_POLICY["set_by"] = "Risk-Alpha"

        trading = _make_trading()  # available=8_000_000
        tools, _, _, _ = build_agent_tools(trading=trading, agent_name="Trader-X")
        set_tool = next(t for t in tools if t.name == "set_position_policy")
        await set_tool.coroutine(max_per_trade_pct=0.20)

        submit_tool = next(t for t in tools if t.name == "submit_order")
        # 8_000_000 * 20% = 1_600_000 max. 100 × 70000 = 7_000_000 → blocked
        result = await submit_tool.coroutine(
            symbol="005930", side="buy", quantity=100, price=70000.0, market="kr_stock"
        )
        assert result.startswith("ERR:position_policy")
        assert "20%" in result

        # Reset policy
        dq._POSITION_POLICY["max_per_trade_pct"] = None

    @pytest.mark.asyncio
    async def test_position_policy_allows_sized_order(self):
        from agentic_capital.core.tools import data_query as dq
        trading = _make_trading()  # available=8_000_000
        tools, _, _, _ = build_agent_tools(trading=trading, agent_name="Trader-X")
        set_tool = next(t for t in tools if t.name == "set_position_policy")
        await set_tool.coroutine(max_per_trade_pct=0.20)  # max 1_600_000

        submit_tool = next(t for t in tools if t.name == "submit_order")
        # 10 × 70000 = 700_000 < 1_600_000 → allowed
        result = await submit_tool.coroutine(
            symbol="005930", side="buy", quantity=10, price=70000.0, market="kr_stock"
        )
        assert "submitted" in result
        # Reset
        dq._POSITION_POLICY["max_per_trade_pct"] = None

    @pytest.mark.asyncio
    async def test_hire_agent_tool_records_decision(self):
        tools, decisions, _, _ = build_agent_tools(agent_name="CEO-Alpha")
        tool = next(t for t in tools if t.name == "hire_agent")
        result = await tool.coroutine(
            role="trader", name="Trader-Delta", capital=2_000_000,
            philosophy="Aggressive momentum strategy"
        )
        assert "hire_queued" in result
        assert "Trader-Delta" in result
        assert len(decisions) == 1
        assert decisions[0]["type"] == "hire"
        assert decisions[0]["target"] == "Trader-Delta"
        assert decisions[0]["role"] == "trader"
        assert decisions[0]["capital"] == 2_000_000

    @pytest.mark.asyncio
    async def test_fire_agent_tool_records_decision(self):
        tools, decisions, _, _ = build_agent_tools(agent_name="CEO-Alpha")
        tool = next(t for t in tools if t.name == "fire_agent")
        result = await tool.coroutine(target_name="Analyst-Beta", reason="Underperforming")
        assert "fire_queued" in result
        assert "Analyst-Beta" in result
        assert len(decisions) == 1
        assert decisions[0]["type"] == "fire"
        assert decisions[0]["target"] == "Analyst-Beta"

    @pytest.mark.asyncio
    async def test_create_role_tool_records_decision(self):
        tools, decisions, _, _ = build_agent_tools(agent_name="CEO-Alpha")
        tool = next(t for t in tools if t.name == "create_role")
        result = await tool.coroutine(
            role_name="risk_manager",
            description="Manages portfolio risk and drawdown limits",
            permissions=["analyze", "send_message"],
        )
        assert "role_queued" in result
        assert "risk_manager" in result
        assert len(decisions) == 1
        assert decisions[0]["type"] == "create_role"
        assert decisions[0]["detail"] == "risk_manager"
