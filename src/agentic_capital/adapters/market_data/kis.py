"""KIS market data adapter — Korean stock price and OHLCV data."""

from __future__ import annotations

from datetime import datetime

import structlog

from agentic_capital.adapters.kis_session import KISSession
from agentic_capital.ports.market_data import OHLCV, MarketDataPort, Quote

logger = structlog.get_logger()


class KISMarketDataAdapter(MarketDataPort):
    """KIS Open API adapter for Korean stock market data."""

    def __init__(self, *, session: KISSession | None = None) -> None:
        if session is None:
            session = KISSession()
        self._session = session
        logger.info(
            "kis_market_data_initialized",
            mode="paper" if session.is_paper else "live",
        )

    async def get_quote(self, symbol: str) -> Quote:
        """Get current price quote for a Korean stock."""
        await self._session.ensure_token()
        try:
            r = await self._session.get(
                f"{self._session.base_url}/uapi/domestic-stock/v1/quotations/inquire-price",
                headers=self._session.headers("FHKST01010100"),
                params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol},
            )
            data = r.json()
            if data.get("rt_cd") != "0":
                raise RuntimeError(f"KIS quote failed: {data.get('msg1', data)}")

            o = data.get("output", {})
            return Quote(
                symbol=symbol,
                price=float(o.get("stck_prpr", 0)),
                bid=float(o.get("bidp1", 0)) if o.get("bidp1") else None,
                ask=float(o.get("askp1", 0)) if o.get("askp1") else None,
                volume=float(o.get("acml_vol", 0)),
                timestamp=datetime.now(),
            )
        except Exception:
            logger.exception("kis_get_quote_failed", symbol=symbol)
            raise

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        limit: int = 100,
    ) -> list[OHLCV]:
        """Get historical daily OHLCV data for a Korean stock."""
        await self._session.ensure_token()
        try:
            today = datetime.now().strftime("%Y%m%d")
            r = await self._session.get(
                f"{self._session.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-price",
                headers=self._session.headers("FHKST01010400"),
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": symbol,
                    "FID_INPUT_DATE_1": "",
                    "FID_INPUT_DATE_2": today,
                    "FID_PERIOD_DIV_CODE": "D",
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
        except Exception:
            logger.exception("kis_get_ohlcv_failed", symbol=symbol)
            raise

    async def get_symbols(self) -> list[str]:
        """Return major Korean stock symbols (static list for Phase 1)."""
        return [
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
        ]
