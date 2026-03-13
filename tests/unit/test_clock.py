"""Unit tests for multi-market clock."""

from datetime import datetime, timedelta, timezone

import pytest

from agentic_capital.simulation.clock import (
    EST,
    KST,
    get_open_markets,
    is_market_open,
    is_market_open_for,
    now_kst,
    seconds_until_market_open,
)


class TestIsMarketOpenFor:
    def test_krx_monday_morning(self):
        dt = datetime(2026, 3, 16, 10, 0, tzinfo=KST)
        assert is_market_open_for("KRX", dt) is True

    def test_krx_at_close(self):
        dt = datetime(2026, 3, 16, 15, 30, tzinfo=KST)
        assert is_market_open_for("KRX", dt) is False

    def test_nasdaq_open(self):
        dt = datetime(2026, 3, 16, 10, 0, tzinfo=EST)
        assert is_market_open_for("NASDAQ", dt) is True

    def test_nasdaq_before_open(self):
        dt = datetime(2026, 3, 16, 9, 0, tzinfo=EST)
        assert is_market_open_for("NASDAQ", dt) is False

    def test_nasdaq_at_close(self):
        dt = datetime(2026, 3, 16, 16, 0, tzinfo=EST)
        assert is_market_open_for("NASDAQ", dt) is False

    def test_nyse_open(self):
        dt = datetime(2026, 3, 16, 12, 0, tzinfo=EST)
        assert is_market_open_for("NYSE", dt) is True

    def test_weekend_all_closed(self):
        dt = datetime(2026, 3, 21, 12, 0, tzinfo=KST)  # Saturday
        assert is_market_open_for("KRX", dt) is False
        assert is_market_open_for("NASDAQ", dt) is False

    def test_unknown_market(self):
        dt = datetime(2026, 3, 16, 10, 0, tzinfo=KST)
        assert is_market_open_for("UNKNOWN", dt) is False


class TestIsMarketOpen:
    def test_krx_hours_only(self):
        # Monday 10:00 KST = Monday 01:00 EST → KRX open, US closed
        dt = datetime(2026, 3, 16, 10, 0, tzinfo=KST)
        assert is_market_open(dt) is True

    def test_us_hours_only(self):
        # Monday 23:30 KST = Monday 10:30 EST → KRX closed, US open
        dt = datetime(2026, 3, 16, 23, 30, tzinfo=KST)
        assert is_market_open(dt) is True

    def test_all_closed(self):
        # Saturday
        dt = datetime(2026, 3, 21, 12, 0, tzinfo=KST)
        assert is_market_open(dt) is False

    def test_gap_between_markets(self):
        # Monday 17:00 KST = Monday 04:00 EST → both closed
        dt = datetime(2026, 3, 16, 17, 0, tzinfo=KST)
        assert is_market_open(dt) is False


class TestGetOpenMarkets:
    def test_krx_open(self):
        dt = datetime(2026, 3, 16, 10, 0, tzinfo=KST)
        markets = get_open_markets(dt)
        assert "KRX" in markets
        assert "NASDAQ" not in markets

    def test_us_open(self):
        dt = datetime(2026, 3, 16, 23, 30, tzinfo=KST)
        markets = get_open_markets(dt)
        assert "NASDAQ" in markets
        assert "NYSE" in markets
        assert "KRX" not in markets

    def test_none_open(self):
        dt = datetime(2026, 3, 21, 12, 0, tzinfo=KST)
        assert get_open_markets(dt) == []


class TestSecondsUntilMarketOpen:
    def test_already_open(self):
        dt = datetime(2026, 3, 16, 10, 0, tzinfo=KST)
        assert seconds_until_market_open(dt) == 0

    def test_before_krx_open(self):
        dt = datetime(2026, 3, 16, 8, 0, tzinfo=KST)
        # 1 hour until KRX 09:00
        assert seconds_until_market_open(dt) == 3600

    def test_saturday(self):
        dt = datetime(2026, 3, 21, 12, 0, tzinfo=KST)
        result = seconds_until_market_open(dt)
        assert result > 0


class TestNowKst:
    def test_returns_kst(self):
        dt = now_kst()
        assert dt.tzinfo is not None
        assert dt.utcoffset() == timedelta(hours=9)
