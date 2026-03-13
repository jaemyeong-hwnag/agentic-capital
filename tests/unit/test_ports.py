"""Tests for Port interfaces — MarketDataPort, LLMPort."""

from datetime import datetime

from agentic_capital.ports.llm import LLMPort
from agentic_capital.ports.market_data import OHLCV, MarketDataPort, Quote


class TestOHLCV:
    def test_create(self) -> None:
        candle = OHLCV(
            timestamp=datetime(2026, 3, 13),
            open=150.0,
            high=155.0,
            low=148.0,
            close=153.0,
            volume=1_000_000,
        )
        assert candle.close == 153.0


class TestQuote:
    def test_create(self) -> None:
        q = Quote(symbol="AAPL", price=150.0)
        assert q.symbol == "AAPL"
        assert q.bid is None

    def test_full(self) -> None:
        q = Quote(
            symbol="AAPL",
            price=150.0,
            bid=149.9,
            ask=150.1,
            volume=500_000,
            timestamp=datetime(2026, 3, 13),
        )
        assert q.bid == 149.9
        assert q.ask == 150.1


class TestMarketDataPortABC:
    def test_is_abstract(self) -> None:
        assert hasattr(MarketDataPort, "get_quote")
        assert hasattr(MarketDataPort, "get_ohlcv")
        assert hasattr(MarketDataPort, "get_symbols")


class TestLLMPortABC:
    def test_is_abstract(self) -> None:
        assert hasattr(LLMPort, "generate")
        assert hasattr(LLMPort, "embed")
