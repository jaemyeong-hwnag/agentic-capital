"""Unit tests for YFinanceMarketDataAdapter."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from agentic_capital.adapters.market_data.yfinance_adapter import (
    YFinanceMarketDataAdapter,
    _resolve_symbol,
)


class TestResolveSymbol:
    def test_korean_6digit(self):
        assert _resolve_symbol("005930") == ["005930.KS", "005930.KQ"]

    def test_us_ticker(self):
        assert _resolve_symbol("AAPL") == ["AAPL"]

    def test_lowercase_normalized(self):
        assert _resolve_symbol("aapl") == ["AAPL"]

    def test_non_digit_6char(self):
        assert _resolve_symbol("GOOGLE") == ["GOOGLE"]

    def test_strip_whitespace(self):
        assert _resolve_symbol(" 005930 ") == ["005930.KS", "005930.KQ"]


class TestYFinanceMarketDataAdapter:
    def _make_adapter(self):
        return YFinanceMarketDataAdapter()

    @pytest.mark.asyncio
    async def test_get_quote_success(self):
        adapter = self._make_adapter()
        mock_fi = MagicMock()
        mock_fi.last_price = 75000.0
        mock_fi.currency = "KRW"
        mock_fi.bid = 74900.0
        mock_fi.ask = 75100.0
        mock_fi.three_month_average_volume = 12000000.0

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker = MagicMock()
            mock_ticker.fast_info = mock_fi
            mock_ticker_cls.return_value = mock_ticker

            result = await adapter.get_quote("005930")

        assert result.symbol == "005930"
        assert result.price == 75000.0
        assert result.currency == "KRW"
        assert result.market == "kr_stock"

    @pytest.mark.asyncio
    async def test_get_quote_fallback_to_kosdaq(self):
        adapter = self._make_adapter()

        call_count = 0

        def ticker_side_effect(sym):
            nonlocal call_count
            call_count += 1
            mock_fi = MagicMock()
            if sym.endswith(".KS"):
                mock_fi.last_price = None
                mock_fi.previous_close = None
            else:
                mock_fi.last_price = 50000.0
                mock_fi.currency = "KRW"
                mock_fi.bid = None
                mock_fi.ask = None
                mock_fi.three_month_average_volume = None
            t = MagicMock()
            t.fast_info = mock_fi
            return t

        with patch("yfinance.Ticker", side_effect=ticker_side_effect):
            result = await adapter.get_quote("035720")

        assert result.price == 50000.0
        assert call_count == 2  # tried .KS then .KQ

    @pytest.mark.asyncio
    async def test_get_quote_no_data_raises(self):
        adapter = self._make_adapter()
        mock_fi = MagicMock()
        mock_fi.last_price = None
        mock_fi.previous_close = None

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker = MagicMock()
            mock_ticker.fast_info = mock_fi
            mock_ticker_cls.return_value = mock_ticker

            with pytest.raises(RuntimeError, match="no data"):
                await adapter.get_quote("999999")

    @pytest.mark.asyncio
    async def test_get_ohlcv_success(self):
        import pandas as pd

        adapter = self._make_adapter()
        df = pd.DataFrame(
            {
                "Open": [74000.0, 74500.0],
                "High": [75500.0, 75800.0],
                "Low": [73800.0, 74200.0],
                "Close": [75000.0, 75300.0],
                "Volume": [10000000.0, 12000000.0],
            },
            index=pd.to_datetime(["2026-03-14", "2026-03-15"]),
        )
        df.index = df.index.tz_localize("UTC")

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = df
            mock_ticker_cls.return_value = mock_ticker

            result = await adapter.get_ohlcv("005930", timeframe="1d", limit=20)

        assert len(result) == 2
        assert result[0].close == 75000.0
        assert result[1].volume == 12000000.0

    @pytest.mark.asyncio
    async def test_get_ohlcv_empty_returns_empty_list(self):
        import pandas as pd

        adapter = self._make_adapter()
        empty_df = pd.DataFrame()

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker = MagicMock()
            mock_ticker.history.return_value = empty_df
            mock_ticker_cls.return_value = mock_ticker

            result = await adapter.get_ohlcv("999999", timeframe="1d")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_symbols_returns_empty(self):
        adapter = self._make_adapter()
        result = await adapter.get_symbols()
        assert result == []
