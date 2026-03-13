"""Unit tests for data query tools."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentic_capital.core.tools.data_query import DataQueryTools


def _make_trading():
    trading = MagicMock()
    trading.get_balance = AsyncMock(
        return_value=MagicMock(total=10_000_000, available=8_000_000, currency="KRW")
    )
    trading.get_positions = AsyncMock(return_value=[
        MagicMock(
            symbol="005930", quantity=100, avg_price=70000,
            current_price=72000, unrealized_pnl=200000, unrealized_pnl_pct=2.86,
        ),
    ])
    return trading


def _make_market_data():
    md = MagicMock()
    md.get_quote = AsyncMock(
        return_value=MagicMock(price=72000, bid=71900, ask=72100, volume=5_000_000)
    )
    md.get_ohlcv = AsyncMock(return_value=[
        MagicMock(timestamp=datetime(2026, 1, 1), open=70000, high=73000, low=69000, close=72000, volume=3_000_000),
    ])
    md.get_symbols = AsyncMock(return_value=["005930", "000660", "035720"])
    return md


class TestDataQueryTools:
    @pytest.mark.asyncio
    async def test_query_balance(self):
        tools = DataQueryTools(trading=_make_trading())
        result = await tools.query_balance()
        assert result["total"] == 10_000_000
        assert result["available"] == 8_000_000
        assert result["currency"] == "KRW"

    @pytest.mark.asyncio
    async def test_query_balance_no_adapter(self):
        tools = DataQueryTools()
        result = await tools.query_balance()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_query_positions(self):
        tools = DataQueryTools(trading=_make_trading())
        result = await tools.query_positions()
        assert len(result) == 1
        assert result[0]["symbol"] == "005930"
        assert result[0]["unrealized_pnl_pct"] == 2.86

    @pytest.mark.asyncio
    async def test_query_positions_no_adapter(self):
        tools = DataQueryTools()
        result = await tools.query_positions()
        assert result == []

    @pytest.mark.asyncio
    async def test_query_quote(self):
        tools = DataQueryTools(market_data=_make_market_data())
        result = await tools.query_quote("005930")
        assert result["price"] == 72000
        assert result["symbol"] == "005930"

    @pytest.mark.asyncio
    async def test_query_quote_no_adapter(self):
        tools = DataQueryTools()
        result = await tools.query_quote("005930")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_query_quotes(self):
        tools = DataQueryTools(market_data=_make_market_data())
        result = await tools.query_quotes(["005930", "000660"])
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_query_ohlcv(self):
        tools = DataQueryTools(market_data=_make_market_data())
        result = await tools.query_ohlcv("005930", limit=1)
        assert len(result) == 1
        assert result[0]["close"] == 72000

    @pytest.mark.asyncio
    async def test_query_ohlcv_no_adapter(self):
        tools = DataQueryTools()
        result = await tools.query_ohlcv("005930")
        assert result == []

    @pytest.mark.asyncio
    async def test_query_symbols(self):
        tools = DataQueryTools(market_data=_make_market_data())
        result = await tools.query_symbols()
        assert "005930" in result
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_query_symbols_no_adapter(self):
        tools = DataQueryTools()
        result = await tools.query_symbols()
        assert result == []

    def test_get_tool_descriptions(self):
        tools = DataQueryTools()
        descriptions = tools.get_tool_descriptions()
        assert len(descriptions) == 6
        names = [d["name"] for d in descriptions]
        assert "query_balance" in names
        assert "query_positions" in names
        assert "query_quote" in names
        assert "query_ohlcv" in names
        assert "query_symbols" in names

    @pytest.mark.asyncio
    async def test_execute_tool(self):
        tools = DataQueryTools(trading=_make_trading())
        result = await tools.execute_tool("query_balance")
        assert result["total"] == 10_000_000

    @pytest.mark.asyncio
    async def test_execute_tool_with_params(self):
        tools = DataQueryTools(market_data=_make_market_data())
        result = await tools.execute_tool("query_quote", symbol="005930")
        assert result["price"] == 72000

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        tools = DataQueryTools()
        result = await tools.execute_tool("nonexistent_tool")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_query_balance_error_handling(self):
        trading = MagicMock()
        trading.get_balance = AsyncMock(side_effect=Exception("connection failed"))
        tools = DataQueryTools(trading=trading)
        result = await tools.query_balance()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_query_positions_error_handling(self):
        trading = MagicMock()
        trading.get_positions = AsyncMock(side_effect=Exception("timeout"))
        tools = DataQueryTools(trading=trading)
        result = await tools.query_positions()
        assert result == []

    @pytest.mark.asyncio
    async def test_query_quote_error_handling(self):
        md = MagicMock()
        md.get_quote = AsyncMock(side_effect=Exception("symbol not found"))
        tools = DataQueryTools(market_data=md)
        result = await tools.query_quote("INVALID")
        assert "error" in result
