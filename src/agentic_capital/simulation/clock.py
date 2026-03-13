"""Market clock — KRX trading hours and session management."""

from __future__ import annotations

from datetime import datetime, time, timezone, timedelta

KST = timezone(timedelta(hours=9))

# KRX (한국거래소) trading hours
_MARKET_OPEN = time(9, 0)
_MARKET_CLOSE = time(15, 30)

# Weekdays: Monday=0 ... Friday=4
_TRADING_DAYS = {0, 1, 2, 3, 4}


def now_kst() -> datetime:
    """Get current time in KST."""
    return datetime.now(KST)


def is_market_open(dt: datetime | None = None) -> bool:
    """Check if the Korean stock market is open.

    Does not account for public holidays (Phase 2).
    """
    if dt is None:
        dt = now_kst()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)

    if dt.weekday() not in _TRADING_DAYS:
        return False

    return _MARKET_OPEN <= dt.time() < _MARKET_CLOSE


def seconds_until_market_open(dt: datetime | None = None) -> int:
    """Return seconds until next market open. 0 if already open."""
    if dt is None:
        dt = now_kst()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)

    if is_market_open(dt):
        return 0

    # Find next trading day
    target = dt.replace(hour=9, minute=0, second=0, microsecond=0)

    if dt.time() >= _MARKET_CLOSE or dt.weekday() not in _TRADING_DAYS:
        # Move to next day
        target += timedelta(days=1)

    # Skip weekends
    while target.weekday() not in _TRADING_DAYS:
        target += timedelta(days=1)

    diff = (target - dt).total_seconds()
    return max(0, int(diff))
