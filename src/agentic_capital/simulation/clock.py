"""Market clock — multi-market trading hours and session management.

Supports KRX, NASDAQ, NYSE, and other markets.
The system checks ALL markets — if any market is open, trading is possible.
No restrictions on which markets agents can trade.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

KST = timezone(timedelta(hours=9))
EST = timezone(timedelta(hours=-5))  # US Eastern (simplified, no DST)
UTC = timezone.utc

# Weekdays: Monday=0 ... Friday=4
_TRADING_DAYS = {0, 1, 2, 3, 4}

# Market sessions: (open_time, close_time, timezone)
MARKETS = {
    "KRX": (time(9, 0), time(15, 30), KST),       # 한국거래소
    "NASDAQ": (time(9, 30), time(16, 0), EST),      # 나스닥
    "NYSE": (time(9, 30), time(16, 0), EST),         # 뉴욕증권거래소
}


def now_kst() -> datetime:
    """Get current time in KST."""
    return datetime.now(KST)


def is_market_open_for(market: str, dt: datetime | None = None) -> bool:
    """Check if a specific market is open."""
    if market not in MARKETS:
        return False

    open_time, close_time, tz = MARKETS[market]

    if dt is None:
        dt = datetime.now(tz)
    else:
        dt = dt.astimezone(tz)

    if dt.weekday() not in _TRADING_DAYS:
        return False

    return open_time <= dt.time() < close_time


def is_market_open(dt: datetime | None = None) -> bool:
    """Check if ANY supported market is currently open.

    Returns True if at least one market is trading.
    """
    return any(is_market_open_for(m, dt) for m in MARKETS)


def get_open_markets(dt: datetime | None = None) -> list[str]:
    """Return list of currently open markets."""
    return [m for m in MARKETS if is_market_open_for(m, dt)]


def seconds_until_market_open(dt: datetime | None = None) -> int:
    """Return seconds until next market open across all markets. 0 if any is already open."""
    if is_market_open(dt):
        return 0

    if dt is None:
        dt = datetime.now(UTC)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    min_wait = float("inf")

    for _market, (open_time, _close_time, tz) in MARKETS.items():
        local_dt = dt.astimezone(tz)
        target = local_dt.replace(hour=open_time.hour, minute=open_time.minute, second=0, microsecond=0)

        if local_dt.time() >= open_time:
            # Already past open today, try next day
            target += timedelta(days=1)

        # Skip weekends
        while target.weekday() not in _TRADING_DAYS:
            target += timedelta(days=1)

        diff = (target - local_dt).total_seconds()
        if diff < min_wait:
            min_wait = diff

    return max(0, int(min_wait))
