"""Unit tests for data query tools."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentic_capital.core.tools.data_query import (
    DataQueryTools,
    _market_signal_from_ohlcv,
    collect_finance_decision_tool_results,
)


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
    async def test_query_quote_rejects_market_session_labels_before_adapter(self):
        market_data = _make_market_data()
        tools = DataQueryTools(market_data=market_data)

        result = await tools.query_quote("NASDAQ:CLOSED")

        assert result == {"error": "invalid_symbol:market_session_label", "symbol": "NASDAQ:CLOSED"}
        market_data.get_quote.assert_not_awaited()

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
    async def test_query_ohlcv_rejects_placeholder_before_adapter(self):
        market_data = _make_market_data()
        tools = DataQueryTools(market_data=market_data)

        result = await tools.query_ohlcv("unspecified")

        assert result == []
        market_data.get_ohlcv.assert_not_awaited()

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


@pytest.mark.asyncio
async def test_collect_finance_decision_tool_results_treats_us_premarket_as_open():
    result = await collect_finance_decision_tool_results(
        tool_plan_payload={"tool_plan": [{"tool": "get_market_session"}, {"tool": "get_quote"}]},
        trading=_make_trading(),
        market_data=_make_market_data(),
        symbol="AAPL",
        market="us_stock",
        open_markets=["NASDAQ_PRE"],
        capital_limit=1_000_000,
    )

    assert result["get_market_session"]["exchange"] == "NASDAQ"
    assert result["get_market_session"]["is_open"] is True
    assert result["get_market_session"]["state"] == "pre"
    assert result["get_market_session"]["regular_session"] is False


@pytest.mark.asyncio
async def test_collect_finance_decision_tool_results_marks_nxt_premarket_open_but_not_regular():
    result = await collect_finance_decision_tool_results(
        tool_plan_payload={"tool_plan": [{"tool": "get_market_session"}, {"tool": "get_quote"}]},
        trading=_make_trading(),
        market_data=_make_market_data(),
        symbol="005930",
        market="kr_stock",
        open_markets=["NXT_PRE"],
        capital_limit=1_000_000,
    )

    assert result["get_market_session"]["exchange"] == "NXT"
    assert result["get_market_session"]["is_open"] is True
    assert result["get_market_session"]["regular_session"] is False
    assert result["get_market_session"]["session"] == "nxt_pre"


@pytest.mark.asyncio
async def test_collect_finance_decision_tool_results_marks_night_session_open_for_kr_options():
    result = await collect_finance_decision_tool_results(
        tool_plan_payload={"tool_plan": [{"tool": "get_market_session"}]},
        trading=_make_trading(),
        market_data=_make_market_data(),
        symbol="K200_CALL_ATM",
        market="kr_options",
        open_markets=["NIGHT"],
        capital_limit=1_000_000,
    )

    assert result["get_market_session"]["exchange"] == "NIGHT"
    assert result["get_market_session"]["is_open"] is True
    assert result["get_market_session"]["state"] == "night"
    assert result["get_market_session"]["regular_session"] is False


@pytest.mark.asyncio
async def test_collect_finance_decision_tool_results_adds_structured_payload():
    result = await collect_finance_decision_tool_results(
        tool_plan_payload={
            "tool_plan": [
                {"tool": "search_rag"},
                {"tool": "get_market_session"},
                {"tool": "get_balance"},
                {"tool": "get_positions"},
                {"tool": "get_quote", "args": {"symbol": "005930"}},
                {"tool": "get_risk_limit"},
            ],
        },
        trading=_make_trading(),
        market_data=_make_market_data(),
        symbol="005930",
        market="kr_stock",
        open_markets=["KRX"],
        capital_limit=1_000_000,
        evidence=[{"doc_id": "ev-1", "text": "risk policy " + ("x" * 1000)}],
    )

    payload = result["finance_decision_payload"]
    assert payload["balance"]["available"] == 1_000_000
    assert payload["balance"]["source"] == "effective_capital_limit"
    assert payload["balance"]["broker_balance"]["available"] == 8_000_000
    assert payload["positions"][0]["symbol"] == "005930"
    assert payload["quote"]["price"] == 72000
    assert payload["market_session"]["is_open"] is True
    assert payload["risk_limit"]["paper_trade_only"] is True
    assert payload["rag"]["evidence_ids"] == ["ev-1"]
    assert payload["rag"]["evidence"][0]["id"] == "ev-1"
    assert payload["rag"]["evidence"][0]["preview"].endswith("...")
    assert "x" * 500 not in str(payload["rag"]["evidence"])
    assert set(payload["tool_results"]) >= {
        "search_rag",
        "get_market_session",
        "get_balance",
        "get_positions",
        "get_quote",
        "get_risk_limit",
    }


@pytest.mark.asyncio
async def test_collect_finance_decision_tool_results_records_inner_broker_balance() -> None:
    guarded = _make_trading()
    guarded.get_balance.return_value = MagicMock(total=5_000_000, available=5_000_000, currency="KRW")
    guarded._inner = MagicMock()
    guarded._inner.get_balance = AsyncMock(
        return_value=MagicMock(total=49_707_530, available=49_707_530, currency="KRW")
    )

    result = await collect_finance_decision_tool_results(
        tool_plan_payload={"tool_plan": [{"tool": "get_balance"}]},
        trading=guarded,
        market_data=_make_market_data(),
        symbol="005930",
        market="kr_stock",
        capital_limit=5_000_000,
    )

    balance = result["finance_decision_payload"]["balance"]
    assert balance["available"] == 5_000_000
    assert balance["source"] == "effective_capital_limit"
    assert balance["broker_balance"]["available"] == 49_707_530


def test_market_signal_marks_recent_positive_reversal_as_buy_candidate() -> None:
    signal = _market_signal_from_ohlcv(
        [
            {"close": 100.25},
            {"close": 100.0},
            {"close": 100.0},
            {"close": 100.0},
        ],
        {"price": 100.2},
    )

    assert signal["candidate_action"] == "BUY"
    assert signal["reason"] == "recent_positive_reversal"
    assert signal["confidence"] > 0


def test_market_signal_marks_window_positive_momentum_as_buy_candidate() -> None:
    signal = _market_signal_from_ohlcv(
        [
            {"close": 100.0},
            {"close": 100.6},
            {"close": 100.6},
            {"close": 100.6},
        ],
        {"price": 100.6},
    )

    assert signal["candidate_action"] == "BUY"
    assert signal["reason"] == "window_positive_momentum"
    assert signal["confidence"] > 0
