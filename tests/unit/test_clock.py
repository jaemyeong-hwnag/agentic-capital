"""Unit tests for market clock."""

from datetime import datetime, timezone, timedelta

import pytest

from agentic_capital.simulation.clock import (
    KST,
    is_market_open,
    now_kst,
    seconds_until_market_open,
)


class TestIsMarketOpen:
    def test_monday_morning(self):
        # Monday 10:00 KST
        dt = datetime(2026, 3, 16, 10, 0, tzinfo=KST)
        assert is_market_open(dt) is True

    def test_friday_afternoon(self):
        # Friday 15:00 KST
        dt = datetime(2026, 3, 20, 15, 0, tzinfo=KST)
        assert is_market_open(dt) is True

    def test_before_open(self):
        # Monday 08:59 KST
        dt = datetime(2026, 3, 16, 8, 59, tzinfo=KST)
        assert is_market_open(dt) is False

    def test_at_open(self):
        # Monday 09:00 KST
        dt = datetime(2026, 3, 16, 9, 0, tzinfo=KST)
        assert is_market_open(dt) is True

    def test_at_close(self):
        # Monday 15:30 KST — closed (exclusive)
        dt = datetime(2026, 3, 16, 15, 30, tzinfo=KST)
        assert is_market_open(dt) is False

    def test_after_close(self):
        # Monday 16:00 KST
        dt = datetime(2026, 3, 16, 16, 0, tzinfo=KST)
        assert is_market_open(dt) is False

    def test_saturday(self):
        # Saturday 12:00 KST
        dt = datetime(2026, 3, 21, 12, 0, tzinfo=KST)
        assert is_market_open(dt) is False

    def test_sunday(self):
        dt = datetime(2026, 3, 22, 12, 0, tzinfo=KST)
        assert is_market_open(dt) is False

    def test_naive_datetime_treated_as_kst(self):
        # Naive datetime with market hours
        dt = datetime(2026, 3, 16, 10, 0)
        assert is_market_open(dt) is True


class TestSecondsUntilMarketOpen:
    def test_already_open(self):
        dt = datetime(2026, 3, 16, 10, 0, tzinfo=KST)
        assert seconds_until_market_open(dt) == 0

    def test_before_open_same_day(self):
        dt = datetime(2026, 3, 16, 8, 0, tzinfo=KST)
        # 1 hour until 09:00
        assert seconds_until_market_open(dt) == 3600

    def test_after_close(self):
        dt = datetime(2026, 3, 16, 16, 0, tzinfo=KST)
        # Next day 09:00 = 17 hours
        assert seconds_until_market_open(dt) == 17 * 3600

    def test_friday_after_close(self):
        dt = datetime(2026, 3, 20, 16, 0, tzinfo=KST)
        # Next Monday 09:00 = 2 days + 17 hours = 65 hours
        assert seconds_until_market_open(dt) == 65 * 3600

    def test_saturday(self):
        dt = datetime(2026, 3, 21, 12, 0, tzinfo=KST)
        # Next Monday 09:00 = 1 day + 21 hours = 45 hours
        assert seconds_until_market_open(dt) == 45 * 3600


class TestNowKst:
    def test_returns_kst(self):
        dt = now_kst()
        assert dt.tzinfo is not None
        assert dt.utcoffset() == timedelta(hours=9)
