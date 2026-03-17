"""Unit tests for multi-market clock."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from agentic_capital.simulation.clock import (
    ET,
    KST,
    get_open_markets,
    is_market_open,
    is_market_open_for,
    now_kst,
    seconds_until_market_open,
)

# EDT = UTC-4 (DST in effect for March 2026 test dates)
EDT = timezone(timedelta(hours=-4))


class TestIsMarketOpenFor:
    def test_krx_monday_morning(self):
        dt = datetime(2026, 3, 16, 10, 0, tzinfo=KST)
        assert is_market_open_for("KRX", dt) is True

    def test_krx_at_close(self):
        dt = datetime(2026, 3, 16, 15, 30, tzinfo=KST)
        assert is_market_open_for("KRX", dt) is False

    def test_nasdaq_open(self):
        dt = datetime(2026, 3, 16, 10, 0, tzinfo=EDT)
        assert is_market_open_for("NASDAQ", dt) is True

    def test_nasdaq_before_open(self):
        dt = datetime(2026, 3, 16, 9, 0, tzinfo=EDT)
        assert is_market_open_for("NASDAQ", dt) is False

    def test_nasdaq_at_close(self):
        dt = datetime(2026, 3, 16, 16, 0, tzinfo=EDT)
        assert is_market_open_for("NASDAQ", dt) is False

    def test_nyse_open(self):
        dt = datetime(2026, 3, 16, 12, 0, tzinfo=EDT)
        assert is_market_open_for("NYSE", dt) is True

    def test_weekend_all_closed(self):
        dt = datetime(2026, 3, 21, 12, 0, tzinfo=KST)  # Saturday
        assert is_market_open_for("KRX", dt) is False
        assert is_market_open_for("NASDAQ", dt) is False

    def test_unknown_market(self):
        dt = datetime(2026, 3, 16, 10, 0, tzinfo=KST)
        assert is_market_open_for("UNKNOWN", dt) is False

    def test_nasdaq_pre_open(self):
        # 4:00 AM EDT = 17:00 KST → pre-market starts
        dt = datetime(2026, 3, 16, 4, 0, tzinfo=EDT)
        assert is_market_open_for("NASDAQ_PRE", dt) is True

    def test_nasdaq_pre_before_open(self):
        dt = datetime(2026, 3, 16, 3, 59, tzinfo=EDT)
        assert is_market_open_for("NASDAQ_PRE", dt) is False

    def test_nasdaq_pre_ends_at_regular_open(self):
        # Pre-market ends when regular opens
        dt = datetime(2026, 3, 16, 9, 30, tzinfo=EDT)
        assert is_market_open_for("NASDAQ_PRE", dt) is False
        assert is_market_open_for("NASDAQ", dt) is True

    def test_nasdaq_after_open(self):
        dt = datetime(2026, 3, 16, 17, 0, tzinfo=EDT)
        assert is_market_open_for("NASDAQ_AFTER", dt) is True

    def test_nasdaq_after_at_close(self):
        dt = datetime(2026, 3, 16, 20, 0, tzinfo=EDT)
        assert is_market_open_for("NASDAQ_AFTER", dt) is False


class TestIsMarketOpen:
    def test_krx_hours_only(self):
        # Monday 10:00 KST → KRX open, US closed
        dt = datetime(2026, 3, 16, 10, 0, tzinfo=KST)
        assert is_market_open(dt) is True

    def test_us_hours_only(self):
        # Monday 23:30 KST = Monday 10:30 EDT → KRX closed, US regular open
        dt = datetime(2026, 3, 16, 23, 30, tzinfo=KST)
        assert is_market_open(dt) is True

    def test_us_premarket(self):
        # Monday 17:00 KST = Monday 04:00 EDT → pre-market open
        dt = datetime(2026, 3, 16, 17, 0, tzinfo=KST)
        assert is_market_open(dt) is True

    def test_all_closed(self):
        # Saturday
        dt = datetime(2026, 3, 21, 12, 0, tzinfo=KST)
        assert is_market_open(dt) is False

    def test_gap_between_markets(self):
        # Monday 8:00 KST = Sunday 23:00 EDT (weekend) → both closed
        dt = datetime(2026, 3, 16, 8, 0, tzinfo=KST)
        assert is_market_open(dt) is False


class TestGetOpenMarkets:
    def test_krx_open(self):
        dt = datetime(2026, 3, 16, 10, 0, tzinfo=KST)
        markets = get_open_markets(dt)
        assert "KRX" in markets
        assert "NASDAQ" not in markets
        assert "NASDAQ_PRE" not in markets

    def test_us_regular_open(self):
        dt = datetime(2026, 3, 16, 23, 30, tzinfo=KST)
        markets = get_open_markets(dt)
        assert "NASDAQ" in markets
        assert "NYSE" in markets
        assert "KRX" not in markets
        assert "NASDAQ_PRE" not in markets

    def test_us_premarket_open(self):
        # 17:00 KST = 04:00 EDT → pre-market
        dt = datetime(2026, 3, 16, 17, 0, tzinfo=KST)
        markets = get_open_markets(dt)
        assert "NASDAQ_PRE" in markets
        assert "NYSE_PRE" in markets
        assert "NASDAQ" not in markets

    def test_us_aftermarket_open(self):
        # Tuesday 05:00 KST = Monday 16:00 EDT → after-hours
        dt = datetime(2026, 3, 17, 5, 0, tzinfo=KST)
        markets = get_open_markets(dt)
        assert "NASDAQ_AFTER" in markets
        assert "NYSE_AFTER" in markets
        assert "NASDAQ" not in markets

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
