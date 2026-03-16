"""YFinance market data adapter — free, covers KR/US/global equities.

Korean stocks: 6-digit code (005930) → auto-appends .KS (KOSPI) or .KQ (KOSDAQ).
US/overseas:  standard ticker (AAPL, TSLA, etc.).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from functools import lru_cache

import structlog

from agentic_capital.ports.market_data import OHLCV, MarketDataPort, Quote

logger = structlog.get_logger()

# yfinance period/interval mappings
_PERIOD_MAP = {
    "1d": ("5d", "1d"),
    "1w": ("1mo", "1wk"),
    "1mo": ("6mo", "1d"),
    "3mo": ("1y", "1d"),
    "1m": ("1d", "1m"),
    "5m": ("5d", "5m"),
    "15m": ("5d", "15m"),
    "60m": ("1mo", "60m"),
}


def _resolve_symbol(symbol: str) -> list[str]:
    """Return candidate yfinance tickers for a symbol.

    Korean 6-digit codes get .KS (KOSPI) and .KQ (KOSDAQ) variants.
    Everything else is returned as-is.
    """
    s = symbol.strip().upper()
    if s.isdigit() and len(s) == 6:
        return [f"{s}.KS", f"{s}.KQ"]
    return [s]


def _fetch_quote_sync(symbol: str) -> Quote | None:
    """Synchronous yfinance quote fetch (run in executor)."""
    import yfinance as yf

    candidates = _resolve_symbol(symbol)
    for ticker_sym in candidates:
        try:
            t = yf.Ticker(ticker_sym)
            fi = t.fast_info
            price = getattr(fi, "last_price", None) or getattr(fi, "previous_close", None)
            if not price:
                continue
            currency = getattr(fi, "currency", "KRW" if ".KS" in ticker_sym or ".KQ" in ticker_sym else "USD")
            market = "kr_stock" if (".KS" in ticker_sym or ".KQ" in ticker_sym) else "us_stock"
            return Quote(
                symbol=symbol,
                price=float(price),
                bid=getattr(fi, "bid", None) or None,
                ask=getattr(fi, "ask", None) or None,
                volume=getattr(fi, "three_month_average_volume", None) or None,
                timestamp=datetime.now(timezone.utc),
                market=market,
                currency=currency,
            )
        except Exception:
            continue
    return None


def _fetch_ohlcv_sync(symbol: str, timeframe: str, limit: int) -> list[OHLCV]:
    """Synchronous yfinance OHLCV fetch (run in executor)."""
    import yfinance as yf

    period, interval = _PERIOD_MAP.get(timeframe, ("1mo", "1d"))
    candidates = _resolve_symbol(symbol)
    for ticker_sym in candidates:
        try:
            t = yf.Ticker(ticker_sym)
            df = t.history(period=period, interval=interval)
            if df.empty:
                continue
            candles = []
            for ts, row in df.tail(limit).iterrows():
                candles.append(OHLCV(
                    timestamp=ts.to_pydatetime().replace(tzinfo=timezone.utc),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                ))
            return candles
        except Exception:
            continue
    return []


class YFinanceMarketDataAdapter(MarketDataPort):
    """Market data via yfinance — no API key, covers 80k+ global symbols."""

    async def get_quote(self, symbol: str, **kwargs) -> Quote:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _fetch_quote_sync, symbol)
        if result is None:
            raise RuntimeError(f"yfinance: no data for {symbol}")
        logger.debug("yfinance_quote_fetched", symbol=symbol, price=result.price)
        return result

    async def get_ohlcv(self, symbol: str, timeframe: str = "1d", limit: int = 20, **kwargs) -> list[OHLCV]:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _fetch_ohlcv_sync, symbol, timeframe, limit)
        logger.debug("yfinance_ohlcv_fetched", symbol=symbol, timeframe=timeframe, bars=len(result))
        return result

    async def get_symbols(self, market: str = "kr_stock") -> list[str]:
        """Returns empty — yfinance has no symbol listing API."""
        return []
