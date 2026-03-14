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


def _make_market_data():
    md = MagicMock()
    md.get_quote = AsyncMock(
        return_value=MagicMock(
            symbol="005930", price=72000, bid=71900, ask=72100, volume=5_000_000,
            market="kr_stock", currency="KRW",
        )
    )
    md.get_ohlcv = AsyncMock(return_value=[
        MagicMock(timestamp="2026-01-01", open=70000, high=73000, low=69000, close=72000, volume=3_000_000),
    ])
    md.get_symbols = AsyncMock(return_value=["005930", "000660"])
    md.get_order_book = AsyncMock(
        return_value=MagicMock(
            symbol="005930",
            bids=[MagicMock(price=71900, quantity=100)],
            asks=[MagicMock(price=72100, quantity=200)],
            timestamp="2026-01-01",
        )
    )
    md.get_fills = AsyncMock(return_value=[])
    return md


class TestBuildAgentTools:
    """Test build_agent_tools() returns correct tools and they work."""

    def test_returns_tools_and_sinks(self):
        tools, decisions, messages = build_agent_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0
        assert isinstance(decisions, list)
        assert isinstance(messages, list)

    def test_tool_names(self):
        tools, _, _ = build_agent_tools()
        names = {t.name for t in tools}
        assert "get_balance" in names
        assert "get_positions" in names
        assert "get_fills" in names
        assert "submit_order" in names
        assert "cancel_order" in names
        assert "save_memory" in names
        assert "search_memory" in names
        assert "send_message" in names
        # Market data tools are removed — AI finds data autonomously
        assert "get_quote" not in names
        assert "get_ohlcv" not in names
        assert "get_order_book" not in names
        assert "get_symbols" not in names

    @pytest.mark.asyncio
    async def test_get_balance_tool(self):
        trading = _make_trading()
        tools, _, _ = build_agent_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_balance")
        result = await tool.coroutine()
        assert result["total"] == 10_000_000
        assert result["currency"] == "KRW"

    @pytest.mark.asyncio
    async def test_get_balance_no_trading(self):
        tools, _, _ = build_agent_tools()
        tool = next(t for t in tools if t.name == "get_balance")
        result = await tool.coroutine()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_positions_tool(self):
        trading = _make_trading()
        tools, _, _ = build_agent_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_positions")
        result = await tool.coroutine()
        assert len(result) == 1
        assert result[0]["symbol"] == "005930"

    @pytest.mark.asyncio
    async def test_get_fills_tool(self):
        trading = _make_trading()
        tools, _, _ = build_agent_tools(trading=trading)
        tool = next(t for t in tools if t.name == "get_fills")
        result = await tool.coroutine()
        assert len(result) == 1
        assert result[0]["order_id"] == "O1"

    @pytest.mark.asyncio
    async def test_submit_order_tool_records_decision(self):
        trading = _make_trading()
        tools, decisions, _ = build_agent_tools(trading=trading, agent_name="Trader-1")
        tool = next(t for t in tools if t.name == "submit_order")
        result = await tool.coroutine(
            symbol="005930", side="buy", quantity=10, price=70000.0
        )
        assert result["status"] == "submitted"
        assert len(decisions) == 1
        assert decisions[0]["symbol"] == "005930"
        assert decisions[0]["action"] == "BUY"

    @pytest.mark.asyncio
    async def test_submit_order_no_trading(self):
        tools, _, _ = build_agent_tools()
        tool = next(t for t in tools if t.name == "submit_order")
        result = await tool.coroutine(symbol="005930", side="buy", quantity=10)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_cancel_order_tool(self):
        trading = _make_trading()
        tools, _, _ = build_agent_tools(trading=trading)
        tool = next(t for t in tools if t.name == "cancel_order")
        result = await tool.coroutine(order_id="ORDER123")
        assert result["cancelled"] is True

    @pytest.mark.asyncio
    async def test_save_and_search_memory(self):
        memory = {}
        tools, _, _ = build_agent_tools(agent_memory=memory)

        save_tool = next(t for t in tools if t.name == "save_memory")
        search_tool = next(t for t in tools if t.name == "search_memory")

        await save_tool.coroutine(content="Samsung Electronics up 5%", keywords=["005930", "bullish"])
        results = await search_tool.coroutine(query="bullish")
        assert len(results) == 1
        assert "Samsung" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_search_memory_no_match(self):
        memory = {}
        tools, _, _ = build_agent_tools(agent_memory=memory)
        search_tool = next(t for t in tools if t.name == "search_memory")
        results = await search_tool.coroutine(query="nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_send_message_tool(self):
        tools, _, messages = build_agent_tools(agent_name="CEO-Alpha")
        tool = next(t for t in tools if t.name == "send_message")
        result = await tool.coroutine(
            to_agent="Trader-Gamma",
            type="INSTRUCTION",
            content={"action": "buy", "symbol": "005930"},
        )
        assert result["sent"] is True
        assert len(messages) == 1
        assert messages[0]["to"] == "Trader-Gamma"
        assert messages[0]["from"] == "CEO-Alpha"
