"""Market clock — multi-market trading hours and session management.

Supports KRX, NASDAQ, NYSE, and other markets including pre/after-hours.
The system checks ALL markets — if any market is open, trading is possible.
No restrictions on which markets agents can trade.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

KST = timezone(timedelta(hours=9))
ET = ZoneInfo("America/New_York")  # DST-aware Eastern Time (EST/EDT auto-switch)
UTC = timezone.utc

# Weekdays: Monday=0 ... Friday=4
_TRADING_DAYS = {0, 1, 2, 3, 4}

# Market sessions: (open_time, close_time, timezone)
# US pre/after-hours included so agents can trade extended sessions.
MARKETS = {
    "KRX": (time(9, 0), time(15, 30), KST),              # 한국거래소 정규
    "NASDAQ": (time(9, 30), time(16, 0), ET),             # 나스닥 정규
    "NYSE": (time(9, 30), time(16, 0), ET),               # 뉴욕증권거래소 정규
    "NASDAQ_PRE": (time(4, 0), time(9, 30), ET),          # 나스닥 프리마켓
    "NYSE_PRE": (time(4, 0), time(9, 30), ET),            # NYSE 프리마켓
    "NASDAQ_AFTER": (time(16, 0), time(20, 0), ET),       # 나스닥 애프터마켓
    "NYSE_AFTER": (time(16, 0), time(20, 0), ET),         # NYSE 애프터마켓
}

# Overnight sessions that span midnight — handled separately
# KRX 야간선물: 평일 18:00 ~ 익일 05:00 KST
_NIGHT_SESSIONS = {
    "NIGHT": (time(18, 0), time(5, 0), KST),  # 18:00 ~ 익일 05:00 KST
}


def now_kst() -> datetime:
    """Get current time in KST."""
    return datetime.now(KST)


def _is_night_session_open(market: str, dt: datetime | None = None) -> bool:
    """Check overnight sessions that span midnight (e.g. 18:00~05:00)."""
    if market not in _NIGHT_SESSIONS:
        return False
    open_time, close_time, tz = _NIGHT_SESSIONS[market]
    if dt is None:
        dt = datetime.now(tz)
    else:
        dt = dt.astimezone(tz)
    # Night session: weekday required at open side (Mon-Fri 18:00~)
    # or any weekday for the early-morning tail (00:00~05:00)
    t = dt.time()
    if t >= open_time:
        # 18:00~23:59 — must be a trading day
        return dt.weekday() in _TRADING_DAYS
    elif t < close_time:
        # 00:00~05:00 — previous day must have been a trading day
        prev_weekday = (dt.weekday() - 1) % 7
        return prev_weekday in _TRADING_DAYS
    return False


def is_market_open_for(market: str, dt: datetime | None = None) -> bool:
    """Check if a specific market is open."""
    if market in _NIGHT_SESSIONS:
        return _is_night_session_open(market, dt)

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
    """Check if ANY supported market is currently open (including night sessions).

    Returns True if at least one market is trading.
    """
    return bool(get_open_markets(dt))


def get_open_markets(dt: datetime | None = None) -> list[str]:
    """Return list of currently open markets (including night sessions)."""
    regular = [m for m in MARKETS if is_market_open_for(m, dt)]
    night = [m for m in _NIGHT_SESSIONS if _is_night_session_open(m, dt)]
    return regular + night


def seconds_until_market_open(dt: datetime | None = None) -> int:
    """Return seconds until next market open across all markets. 0 if any is already open."""
    if is_market_open(dt):
        return 0

    if dt is None:
        dt = datetime.now(UTC)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    min_wait = float("inf")

    all_sessions = list(MARKETS.items()) + [(k, v) for k, v in _NIGHT_SESSIONS.items()]
    for _market, (open_time, _close_time, tz) in all_sessions:
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
