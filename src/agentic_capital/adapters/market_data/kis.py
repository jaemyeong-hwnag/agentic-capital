"""KIS market data adapter — all markets: domestic, overseas, futures."""

from __future__ import annotations

from datetime import datetime

import structlog

from agentic_capital.adapters.kis_session import KISSession
from agentic_capital.ports.market_data import OHLCV, MarketDataPort, OrderBook, OrderBookLevel, Quote

logger = structlog.get_logger()

# Overseas exchange → market_div_code mapping for KIS APIs
_OVS_EXCHANGE_TO_DIV: dict[str, str] = {
    "NASD": "NAS",   # NASDAQ
    "NYSE": "NYS",   # New York
    "AMEX": "AMS",   # AMEX
    "SEHK": "HKS",   # Hong Kong
    "SHAA": "SHS",   # Shanghai
    "SZAA": "SZS",   # Shenzhen
    "TKSE": "TSE",   # Tokyo
    "HASE": "HNX",   # Hanoi
    "VNSE": "HSX",   # Ho Chi Minh
}

# Default exchange for each market
_MARKET_DEFAULT_EXCHANGE: dict[str, str] = {
    "us_stock": "NASD",
    "hk_stock": "SEHK",
    "cn_stock": "SHAA",
    "jp_stock": "TKSE",
    "vn_stock": "HASE",
}

# Default symbol lists per market (starting set — agents can use any valid code)
_DEFAULT_SYMBOLS: dict[str, list[str]] = {
    "kr_stock": [
        "005930",  # 삼성전자
        "000660",  # SK하이닉스
        "373220",  # LG에너지솔루션
        "207940",  # 삼성바이오로직스
        "005380",  # 현대차
        "000270",  # 기아
        "006400",  # 삼성SDI
        "035420",  # NAVER
        "035720",  # 카카오
        "051910",  # LG화학
    ],
    "us_stock": [
        "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
        "META", "TSLA", "AVGO", "JPM", "LLY",
    ],
    "hk_stock": [
        "00700", "09988", "03690", "01299", "02318",
    ],
    "cn_stock": [
        "600519", "601318", "600036", "000858", "601166",
    ],
    "jp_stock": [
        "7203", "6758", "9984", "8306", "6861",
    ],
    "vn_stock": [
        "VIC", "VHM", "VNM", "HPG", "MSN",
    ],
    "kr_futures": [],
    "kr_options": [],
}

# Timeframe → KIS period_div_code mapping
_TIMEFRAME_TO_PERIOD: dict[str, str] = {
    "1d": "D",
    "1w": "W",
    "1mo": "M",
}

# Minute timeframe → FID_INPUT_HOUR_CLS_CODE mapping
_MINUTE_TIMEFRAME: dict[str, str] = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "10m": "10",
    "15m": "15",
    "30m": "30",
    "60m": "60",
}


class KISMarketDataAdapter(MarketDataPort):
    """KIS Open API adapter for all markets: domestic, overseas, futures."""

    def __init__(self, *, session: KISSession | None = None) -> None:
        if session is None:
            session = KISSession()
        self._session = session
        logger.info(
            "kis_market_data_initialized",
            mode="paper" if session.is_paper else "live",
        )

    async def get_quote(self, symbol: str, **kwargs) -> Quote:
        """Get current price quote.

        kwargs:
            market: str — "kr_stock" (default), "us_stock", "hk_stock", etc.
            exchange: str — KIS exchange code e.g. "NASD", "NYSE", "SEHK"
        """
        market = kwargs.get("market", "kr_stock")
        exchange = kwargs.get("exchange")

        if market == "kr_stock":
            return await self._get_quote_domestic(symbol)
        else:
            exch = exchange or _MARKET_DEFAULT_EXCHANGE.get(market, "NASD")
            return await self._get_quote_overseas(symbol, exch)

    async def _get_quote_domestic(self, symbol: str) -> Quote:
        """Domestic stock current price via FHKST01010100."""
        await self._session.ensure_token()
        r = await self._session.get(
            f"{self._session.base_url}/uapi/domestic-stock/v1/quotations/inquire-price",
            headers=self._session.headers("FHKST01010100"),
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol},
        )
        data = r.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS domestic quote failed: {data.get('msg1', data)}")

        o = data.get("output", {})
        return Quote(
            symbol=symbol,
            price=float(o.get("stck_prpr", 0)),
            bid=float(o.get("bidp1", 0)) if o.get("bidp1") else None,
            ask=float(o.get("askp1", 0)) if o.get("askp1") else None,
            volume=float(o.get("acml_vol", 0)),
            timestamp=datetime.now(),
            market="kr_stock",
            currency="KRW",
        )

    async def _get_quote_overseas(self, symbol: str, exchange: str) -> Quote:
        """Overseas stock current price via HHDFS00000300."""
        await self._session.ensure_token()
        ovs_div = _OVS_EXCHANGE_TO_DIV.get(exchange, exchange)
        r = await self._session.get(
            f"{self._session.base_url}/uapi/overseas-price/v1/quotations/price",
            headers=self._session.headers("HHDFS00000300"),
            params={
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": symbol,
            },
        )
        data = r.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS overseas quote failed [{exchange}:{symbol}]: {data.get('msg1', data)}")

        o = data.get("output", {})
        currency = _exchange_to_currency(exchange)
        return Quote(
            symbol=symbol,
            price=float(o.get("last", 0)),
            bid=float(o.get("bidp", 0)) if o.get("bidp") else None,
            ask=float(o.get("askp", 0)) if o.get("askp") else None,
            volume=float(o.get("tvol", 0)) if o.get("tvol") else None,
            timestamp=datetime.now(),
            market=_exchange_to_market(exchange),
            exchange=exchange,
            currency=currency,
        )

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        limit: int = 100,
        **kwargs,
    ) -> list[OHLCV]:
        """Get historical OHLCV data.

        timeframe: "1d", "1w", "1mo" (daily/weekly/monthly),
                   "1m", "3m", "5m", "10m", "15m", "30m", "60m" (minute — domestic only)
        kwargs:
            market: str — "kr_stock" (default), "us_stock", etc.
            exchange: str — for overseas markets
        """
        market = kwargs.get("market", "kr_stock")
        exchange = kwargs.get("exchange")

        if timeframe in _MINUTE_TIMEFRAME:
            return await self._get_ohlcv_minute(symbol, timeframe, limit)
        elif market == "kr_stock":
            period = _TIMEFRAME_TO_PERIOD.get(timeframe, "D")
            return await self._get_ohlcv_domestic(symbol, period, limit)
        else:
            exch = exchange or _MARKET_DEFAULT_EXCHANGE.get(market, "NASD")
            return await self._get_ohlcv_overseas(symbol, exch, limit)

    async def _get_ohlcv_domestic(self, symbol: str, period: str, limit: int) -> list[OHLCV]:
        """Domestic daily/weekly/monthly OHLCV via FHKST01010400."""
        await self._session.ensure_token()
        today = datetime.now().strftime("%Y%m%d")
        r = await self._session.get(
            f"{self._session.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            headers=self._session.headers("FHKST01010400"),
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": symbol,
                "FID_INPUT_DATE_1": "",
                "FID_INPUT_DATE_2": today,
                "FID_PERIOD_DIV_CODE": period,
                "FID_ORG_ADJ_PRC": "1",
            },
        )
        data = r.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS OHLCV failed: {data.get('msg1', data)}")

        candles = []
        for item in data.get("output", [])[:limit]:
            dt_str = item.get("stck_bsop_date", "")
            if not dt_str:
                continue
            candles.append(OHLCV(
                timestamp=datetime.strptime(dt_str, "%Y%m%d"),
                open=float(item.get("stck_oprc", 0)),
                high=float(item.get("stck_hgpr", 0)),
                low=float(item.get("stck_lwpr", 0)),
                close=float(item.get("stck_clpr", 0)),
                volume=float(item.get("acml_vol", 0)),
            ))
        logger.debug("kis_ohlcv_fetched", symbol=symbol, count=len(candles))
        return candles

    async def _get_ohlcv_minute(self, symbol: str, timeframe: str, limit: int) -> list[OHLCV]:
        """Domestic minute OHLCV via FHKST03010100."""
        await self._session.ensure_token()
        minute_code = _MINUTE_TIMEFRAME[timeframe]
        r = await self._session.get(
            f"{self._session.base_url}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            headers=self._session.headers("FHKST03010100"),
            params={
                "FID_ETC_CLS_CODE": "",
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": symbol,
                "FID_INPUT_HOUR_CLS_CODE": minute_code,
                "FID_PW_DATA_INCU_YN": "N",
            },
        )
        data = r.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS minute OHLCV failed: {data.get('msg1', data)}")

        candles = []
        for item in data.get("output2", [])[:limit]:
            dt_str = item.get("stck_bsop_date", "")
            tm_str = item.get("stck_cntg_hour", "000000")
            if not dt_str:
                continue
            try:
                ts = datetime.strptime(f"{dt_str}{tm_str}", "%Y%m%d%H%M%S")
            except ValueError:
                ts = datetime.strptime(dt_str, "%Y%m%d")
            candles.append(OHLCV(
                timestamp=ts,
                open=float(item.get("stck_oprc", 0)),
                high=float(item.get("stck_hgpr", 0)),
                low=float(item.get("stck_lwpr", 0)),
                close=float(item.get("stck_prpr", 0)),
                volume=float(item.get("cntg_vol", 0)),
            ))
        logger.debug("kis_minute_ohlcv_fetched", symbol=symbol, timeframe=timeframe, count=len(candles))
        return candles

    async def _get_ohlcv_overseas(self, symbol: str, exchange: str, limit: int) -> list[OHLCV]:
        """Overseas daily OHLCV via HHDFS76240000."""
        await self._session.ensure_token()
        today = datetime.now().strftime("%Y%m%d")
        r = await self._session.get(
            f"{self._session.base_url}/uapi/overseas-price/v1/quotations/dailyprice",
            headers=self._session.headers("HHDFS76240000"),
            params={
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": symbol,
                "GUBN": "0",        # 0: daily, 1: weekly, 2: monthly
                "BYMD": today,
                "MODP": "1",        # adjusted price
            },
        )
        data = r.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS overseas OHLCV failed [{exchange}:{symbol}]: {data.get('msg1', data)}")

        candles = []
        for item in data.get("output2", [])[:limit]:
            dt_str = item.get("xymd", "")
            if not dt_str:
                continue
            candles.append(OHLCV(
                timestamp=datetime.strptime(dt_str, "%Y%m%d"),
                open=float(item.get("open", 0)),
                high=float(item.get("high", 0)),
                low=float(item.get("low", 0)),
                close=float(item.get("clos", 0)),
                volume=float(item.get("tvol", 0)),
            ))
        logger.debug("kis_overseas_ohlcv_fetched", symbol=symbol, exchange=exchange, count=len(candles))
        return candles

    async def get_order_book(self, symbol: str, depth: int = 10, **kwargs) -> OrderBook:
        """Get domestic stock order book (호가창) via FHKST01010200.

        Note: depth param is informational — KIS returns up to 10 levels.
        """
        await self._session.ensure_token()
        r = await self._session.get(
            f"{self._session.base_url}/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn",
            headers=self._session.headers("FHKST01010200"),
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol},
        )
        data = r.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS order book failed: {data.get('msg1', data)}")

        o = data.get("output1", {})
        max_levels = min(depth, 10)

        asks = []
        bids = []
        for i in range(1, max_levels + 1):
            ask_price = float(o.get(f"askp{i}", 0))
            ask_qty = float(o.get(f"askp_rsqn{i}", 0))
            bid_price = float(o.get(f"bidp{i}", 0))
            bid_qty = float(o.get(f"bidp_rsqn{i}", 0))
            if ask_price > 0:
                asks.append(OrderBookLevel(price=ask_price, quantity=ask_qty))
            if bid_price > 0:
                bids.append(OrderBookLevel(price=bid_price, quantity=bid_qty))

        return OrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp=datetime.now(),
            market="kr_stock",
        )

    async def get_symbols(self, market: str = "kr_stock") -> list[str]:
        """Return default symbol list for a given market.

        Agents can use any valid symbol — this is just a starting set.
        """
        return _DEFAULT_SYMBOLS.get(market, [])


# Helpers

def _exchange_to_market(exchange: str) -> str:
    """Map exchange code to market string."""
    mapping = {
        "NASD": "us_stock", "NYSE": "us_stock", "AMEX": "us_stock",
        "SEHK": "hk_stock",
        "SHAA": "cn_stock", "SZAA": "cn_stock",
        "TKSE": "jp_stock",
        "HASE": "vn_stock", "VNSE": "vn_stock",
    }
    return mapping.get(exchange, "us_stock")


def _exchange_to_currency(exchange: str) -> str:
    """Map exchange code to currency."""
    mapping = {
        "NASD": "USD", "NYSE": "USD", "AMEX": "USD",
        "SEHK": "HKD",
        "SHAA": "CNY", "SZAA": "CNY",
        "TKSE": "JPY",
        "HASE": "VND", "VNSE": "VND",
    }
    return mapping.get(exchange, "USD")
