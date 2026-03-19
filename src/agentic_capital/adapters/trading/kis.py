"""KIS (한국투자증권) trading adapter — all markets via Open API.

Supported markets:
  - kr_stock   : 국내주식 (KOSPI/KOSDAQ) — paper + real
  - us_stock   : 미국주식 (NYSE/NASDAQ/AMEX) — real only
  - hk_stock   : 홍콩주식 — real only
  - cn_stock   : 중국주식 (상하이/선전) — real only
  - jp_stock   : 일본주식 — real only
  - vn_stock   : 베트남주식 — real only
  - kr_futures : 국내선물 — paper + real
  - kr_options : 국내옵션 — paper + real

KIS paper trading (모의투자) only supports kr_stock and kr_futures/options.
Overseas stock orders require a real trading account.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from agentic_capital.adapters.kis_session import KISSession
from agentic_capital.ports.trading import (
    Balance,
    Market,
    Order,
    OrderResult,
    OrderSide,
    Position,
    TradingPort,
)

logger = structlog.get_logger()


async def _fetch_yfinance_kospi200() -> dict:
    """Fetch KOSPI200 index via Yahoo Finance public API.

    Returns parsed dict with price, open, high, low, volume, change, change_pct.
    Returns {} on failure or when market is closed.
    Module-level function so tests can patch it.
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5EKS200",
                params={"interval": "1m", "range": "1d"},
                headers={"User-Agent": "Mozilla/5.0"},
            )
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return {}
        meta = result[0].get("meta", {})
        price = float(meta.get("regularMarketPrice", 0) or 0)
        if price <= 0:
            return {}
        prev_close = float(meta.get("previousClose", 0) or 0)
        change = price - prev_close if prev_close > 0 else 0.0
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0.0
        indicators = result[0].get("indicators", {}).get("quote", [{}])[0]
        high = max((v for v in (indicators.get("high") or []) if v), default=price)
        low = min((v for v in (indicators.get("low") or []) if v), default=price)
        volume = sum(v or 0 for v in (indicators.get("volume") or []))
        return {
            "price": price,
            "open": float(meta.get("regularMarketOpen", price) or price),
            "high": high,
            "low": low,
            "volume": int(volume),
            "change": change,
            "change_pct": change_pct,
        }
    except Exception:
        logger.exception("yfinance_kospi200_fetch_failed")
        return {}


# ── Domestic stock TR IDs ─────────────────────────────────────────────────────
_KR_TR = {
    "balance":       {"real": "TTTC8434R", "paper": "VTTC8434R"},
    "orderable":     {"real": "TTTC8908R", "paper": "VTTC8908R"},  # 주식매수가능조회
    "order_buy":     {"real": "TTTC0802U", "paper": "VTTC0802U"},
    "order_sell":    {"real": "TTTC0801U", "paper": "VTTC0801U"},
    "order_cancel":  {"real": "TTTC0803U", "paper": "VTTC0803U"},
    "fills":         {"real": "TTTC8001R", "paper": "VTTC8001R"},
}

# ── Overseas stock TR IDs (real only — paper mode not supported by KIS) ───────
_OVS_TR = {
    "order_buy":     "TTTT1002U",   # 해외주식 매수
    "order_sell":    "TTTT1006U",   # 해외주식 매도
    "balance":       "TTTS3012R",   # 해외주식 잔고 조회
    "fills":         "TTTS3035R",   # 해외주식 체결 조회
    "order_cancel":  "TTTT1004U",   # 해외주식 정정취소
}

# ── Futures/Options TR IDs ────────────────────────────────────────────────────
_FUT_TR = {
    "order_buy":     {"real": "TTTO0311U", "paper": "VTFO0101U"},
    "order_sell":    {"real": "TTTO0312U", "paper": "VTFO0101U"},  # same TR_ID, different body
    "balance":       {"real": "CTRP6548R", "paper": "VTFO0003R"},
}

# ── Overseas exchange codes ───────────────────────────────────────────────────
_DEFAULT_EXCHANGE: dict[Market, str] = {
    Market.US_STOCK: "NASD",   # NASDAQ default; can be "NYSE" or "AMEX"
    Market.HK_STOCK: "SEHK",
    Market.CN_STOCK: "SHAA",   # Shanghai default; can be "SZAA" (Shenzhen)
    Market.JP_STOCK: "TKSE",
    Market.VN_STOCK: "HASE",   # Hanoi default; can be "VNSE" (Ho Chi Minh)
}

_OVERSEAS_MARKETS = {Market.US_STOCK, Market.HK_STOCK, Market.CN_STOCK, Market.JP_STOCK, Market.VN_STOCK}
_FUTURES_MARKETS = {Market.KR_FUTURES, Market.KR_OPTIONS}


def _exchange_code(order: Order) -> str:
    """Resolve exchange code for overseas orders."""
    if order.exchange:
        return order.exchange
    return _DEFAULT_EXCHANGE.get(order.market, "NASD")


class KISTradingAdapter(TradingPort):
    """KIS Open API adapter supporting all available markets.

    Domestic stocks support both paper and live modes.
    Overseas stocks require a live (real) trading account.
    Futures/options support both modes (limited paper support).
    """

    def __init__(self, *, session: KISSession | None = None) -> None:
        if session is None:
            session = KISSession()
        self._session = session
        logger.info(
            "kis_adapter_initialized",
            mode="paper" if session.is_paper else "LIVE",
            account=session.account_no,
        )

    def _mode(self) -> str:
        return "paper" if self._session.is_paper else "real"

    def _kr_tr(self, action: str) -> str:
        return _KR_TR[action][self._mode()]

    def _fut_tr(self, action: str) -> str:
        return _FUT_TR[action][self._mode()]

    def _tr_id(self, action: str) -> str:
        """Legacy helper kept for backward compatibility."""
        return _KR_TR[action][self._mode()]

    def _assert_real_for_overseas(self) -> None:
        if self._session.is_paper:
            raise NotImplementedError(
                "ERR:paper_no_overseas|KIS_IS_PAPER=true blocks overseas orders|set KIS_IS_PAPER=false for real account"
            )

    # ── Balance ───────────────────────────────────────────────────────────────

    async def _get_orderable_cash(self) -> float | None:
        """Query actual orderable cash via TTTC8908R (주식매수가능조회).

        This returns the true order-eligible amount after T+2 unsettled deductions,
        which is not available in the standard balance endpoint.
        Returns None on failure (caller falls back to dnca_tot_amt).
        """
        try:
            r = await self._session.get(
                f"{self._session.base_url}/uapi/domestic-stock/v1/trading/inquire-psbl-order",
                headers=self._session.headers(self._kr_tr("orderable")),
                params={
                    "CANO": self._session.cano,
                    "ACNT_PRDT_CD": self._session.prdt_cd,
                    "PDNO": "005930",   # dummy symbol — we only care about cash amount
                    "ORD_UNPR": "0",    # 0 = 시장가 기준
                    "ORD_DVSN": "01",   # 시장가
                    "CMA_EVLU_AMT_ICLD_YN": "N",
                    "OVRS_ICLD_YN": "N",
                },
            )
            data = r.json()
            if data.get("rt_cd") != "0":
                return None
            output = data.get("output", {})
            ord_psbl = output.get("ord_psbl_cash_amt") or output.get("nrcvb_buy_amt")
            return float(ord_psbl) if ord_psbl else None
        except Exception:
            return None

    async def get_balance(self) -> Balance:
        """Get domestic account balance (KRW).

        For overseas USD balance, use get_overseas_balance().
        """
        await self._session.ensure_token()
        try:
            r = await self._session.get(
                f"{self._session.base_url}/uapi/domestic-stock/v1/trading/inquire-balance",
                headers=self._session.headers(self._kr_tr("balance")),
                params={
                    "CANO": self._session.cano,
                    "ACNT_PRDT_CD": self._session.prdt_cd,
                    "AFHR_FLPR_YN": "N",
                    "OFL_YN": "",
                    "INQR_DVSN": "02",
                    "UNPR_DVSN": "01",
                    "FUND_STTL_ICLD_YN": "N",
                    "FNCG_AMT_AUTO_RDPT_YN": "N",
                    "PRCS_DVSN": "01",
                    "CTX_AREA_FK100": "",
                    "CTX_AREA_NK100": "",
                },
            )
            data = r.json()
            if data.get("rt_cd") != "0":
                raise RuntimeError(f"KIS balance failed: {data.get('msg1', data)}")

            o2 = data.get("output2", [{}])
            info = o2[0] if o2 else {}

            # nass_amt = 순자산금액 (현금 + 주식 평가금액 합산 — 실제 총자산)
            # tot_evlu_amt = 총평가금액 (포지션 없으면 0이 될 수 있어 단독 사용 부적합)
            nass = float(info.get("nass_amt") or 0)
            evlu = float(info.get("tot_evlu_amt") or 0)
            total = nass if nass > 0 else evlu

            # Try TTTC8908R for true orderable cash (T+2 settlement-adjusted)
            orderable = await self._get_orderable_cash()

            # Fallback priority: 주식매수가능조회 > ord_psbl_cash_amt > dnca_tot_amt
            # nxdy_excc_amt = 익일정산금액 (T+2 기준 출금가능금액, available의 좋은 대안)
            available = orderable or float(
                info.get("ord_psbl_cash_amt")
                or info.get("nxdy_excc_amt")
                or info.get("dnca_tot_amt")
                or 0
            )

            # 오늘 P&L: 현재 순자산 - 전일 총자산 (bfdy_tot_asst_evlu_amt)
            # 전일 데이터 없는 신규 계좌는 initial_capital 기준으로 fallback
            bfdy_total = float(info.get("bfdy_tot_asst_evlu_amt") or 0)
            if bfdy_total > 0:
                daily_pnl = total - bfdy_total
            else:
                from agentic_capital.config import settings
                daily_pnl = total - settings.initial_capital
            # 오늘 수수료+세금: thdt_tlex_amt
            daily_fee = float(info.get("thdt_tlex_amt") or 0)

            logger.debug(
                "kis_balance_fetched",
                total=total,
                available=available,
                orderable_api=orderable,
                daily_pnl=daily_pnl,
                daily_fee=daily_fee,
                dnca_tot=info.get("dnca_tot_amt"),
                ord_psbl=info.get("ord_psbl_cash_amt"),
                thdt_buy=info.get("thdt_buy_amt"),
                nxdy_excc=info.get("nxdy_excc_amt"),
                prvs_rcdl=info.get("prvs_rcdl_excc_amt"),
                evlu_smtl=info.get("evlu_amt_smtl_amt"),
                nass=info.get("nass_amt"),
                all_keys=list(info.keys()) if info else [],
            )
            return Balance(total=total, available=available, currency="KRW",
                           daily_pnl=daily_pnl, daily_fee=daily_fee)
        except Exception:
            logger.exception("kis_get_balance_failed")
            raise

    async def get_overseas_balance(self, currency: str = "USD") -> Balance:
        """Get overseas stock account balance.

        Args:
            currency: Account currency code (e.g., "USD", "HKD", "CNY", "JPY").

        Raises:
            NotImplementedError: In paper mode.
        """
        self._assert_real_for_overseas()
        await self._session.ensure_token()
        try:
            r = await self._session.get(
                f"{self._session.base_url}/uapi/overseas-stock/v1/trading/inquire-balance",
                headers=self._session.headers(_OVS_TR["balance"]),
                params={
                    "CANO": self._session.cano,
                    "ACNT_PRDT_CD": self._session.prdt_cd,
                    "OVRS_EXCG_CD": "",       # all exchanges
                    "TR_CRCY_CD": currency,
                    "CTX_AREA_FK200": "",
                    "CTX_AREA_NK200": "",
                },
            )
            data = r.json()
            if data.get("rt_cd") != "0":
                raise RuntimeError(f"KIS overseas balance failed: {data.get('msg1', data)}")

            o2 = data.get("output2", [{}])
            info = o2[0] if o2 else {}
            total_krw = float(info.get("tot_evlu_pfls_amt", 0))   # KRW equivalent P&L
            total_foreign = float(info.get("frcr_evlu_amt2", 0))  # Foreign currency total
            available = float(info.get("frcr_dncl_amt_2", 0))     # Available foreign cash

            logger.debug(
                "kis_overseas_balance_fetched",
                currency=currency,
                total_foreign=total_foreign,
                total_krw_pnl=total_krw,
                available=available,
            )
            # daily_pnl = KRW-equivalent unrealized P&L (exchange rate applied by KIS)
            return Balance(total=total_foreign, available=available, currency=currency,
                           daily_pnl=total_krw)
        except Exception:
            logger.exception("kis_get_overseas_balance_failed")
            raise

    # ── Positions ─────────────────────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        """Get all open positions — domestic + overseas + futures combined."""
        domestic = await self._get_domestic_positions()
        if not self._session.is_paper:
            try:
                overseas = await self._get_overseas_positions()
            except Exception:
                logger.warning("kis_overseas_positions_failed_fallback_domestic_only")
                overseas = []
            try:
                futures = await self._get_futures_positions()
            except Exception:
                logger.warning("kis_futures_positions_failed_skipping")
                futures = []
        else:
            overseas = []
            futures = []
        return domestic + overseas + futures

    async def _get_domestic_positions(self) -> list[Position]:
        """국내주식 보유 포지션 조회."""
        await self._session.ensure_token()
        try:
            r = await self._session.get(
                f"{self._session.base_url}/uapi/domestic-stock/v1/trading/inquire-balance",
                headers=self._session.headers(self._kr_tr("balance")),
                params={
                    "CANO": self._session.cano,
                    "ACNT_PRDT_CD": self._session.prdt_cd,
                    "AFHR_FLPR_YN": "N",
                    "OFL_YN": "",
                    "INQR_DVSN": "02",
                    "UNPR_DVSN": "01",
                    "FUND_STTL_ICLD_YN": "N",
                    "FNCG_AMT_AUTO_RDPT_YN": "N",
                    "PRCS_DVSN": "01",
                    "CTX_AREA_FK100": "",
                    "CTX_AREA_NK100": "",
                },
            )
            data = r.json()
            if data.get("rt_cd") != "0":
                raise RuntimeError(f"KIS positions failed: {data.get('msg1', data)}")

            positions = []
            for item in data.get("output1", []):
                qty = float(item.get("hldg_qty", 0))
                if qty <= 0:
                    continue
                positions.append(Position(
                    symbol=item.get("pdno", ""),
                    quantity=qty,
                    avg_price=float(item.get("pchs_avg_pric", 0)),
                    current_price=float(item.get("prpr", 0)),
                    unrealized_pnl=float(item.get("evlu_pfls_amt", 0)),
                    unrealized_pnl_pct=float(item.get("evlu_pfls_rt", 0)),
                    market=Market.KR_STOCK,
                    currency="KRW",
                ))

            logger.debug("kis_domestic_positions_fetched", count=len(positions))
            return positions
        except Exception:
            logger.exception("kis_get_domestic_positions_failed")
            raise

    async def _get_overseas_positions(self) -> list[Position]:
        """해외주식 보유 포지션 조회 (real mode only)."""
        await self._session.ensure_token()
        try:
            r = await self._session.get(
                f"{self._session.base_url}/uapi/overseas-stock/v1/trading/inquire-balance",
                headers=self._session.headers(_OVS_TR["balance"]),
                params={
                    "CANO": self._session.cano,
                    "ACNT_PRDT_CD": self._session.prdt_cd,
                    "OVRS_EXCG_CD": "",       # all exchanges
                    "TR_CRCY_CD": "",
                    "CTX_AREA_FK200": "",
                    "CTX_AREA_NK200": "",
                },
            )
            data = r.json()
            if data.get("rt_cd") != "0":
                raise RuntimeError(f"KIS overseas positions failed: {data.get('msg1', data)}")

            # Map KIS exchange codes to Market enum
            excg_to_market = {
                "NASD": Market.US_STOCK, "NYSE": Market.US_STOCK, "AMEX": Market.US_STOCK,
                "SEHK": Market.HK_STOCK,
                "SHAA": Market.CN_STOCK, "SZAA": Market.CN_STOCK,
                "TKSE": Market.JP_STOCK,
                "HASE": Market.VN_STOCK, "VNSE": Market.VN_STOCK,
            }

            positions = []
            for item in data.get("output1", []):
                qty = float(item.get("ovrs_cblc_qty", 0))
                if qty <= 0:
                    continue
                excg_cd = item.get("ovrs_excg_cd", "")
                market = excg_to_market.get(excg_cd, Market.US_STOCK)
                positions.append(Position(
                    symbol=item.get("ovrs_pdno", ""),
                    quantity=qty,
                    avg_price=float(item.get("pchs_avg_pric", 0)),
                    current_price=float(item.get("now_pric2", 0)),
                    unrealized_pnl=float(item.get("frcr_evlu_pfls_amt", 0)),
                    unrealized_pnl_pct=float(item.get("evlu_pfls_rt", 0)),
                    market=market,
                    exchange=excg_cd or None,
                    currency=item.get("tr_crcy_cd", "USD"),
                ))

            logger.debug("kis_overseas_positions_fetched", count=len(positions))
            return positions
        except Exception:
            logger.exception("kis_get_overseas_positions_failed")
            raise

    async def _get_futures_positions(self) -> list[Position]:
        """국내선물 보유 포지션 조회 (CTFO6118R)."""
        await self._session.ensure_token()
        try:
            r = await self._session.get(
                f"{self._session.base_url}/uapi/domestic-futureoption/v1/trading/inquire-balance",
                headers=self._session.headers(_FUT_TR["balance"][self._mode()]),
                params={
                    "CANO": self._session.cano,
                    "ACNT_PRDT_CD": self._session.prdt_cd,
                    "MGNA_DVSN": "01",
                    "EXCC_STAT_CD": "1",
                    "CTX_AREA_FK200": "",
                    "CTX_AREA_NK200": "",
                },
            )
            data = r.json()
            if data.get("rt_cd") != "0":
                logger.debug("kis_futures_positions_empty", msg=data.get("msg1", ""))
                return []

            from agentic_capital.ports.trading import FuturesPosition
            positions = []
            for item in data.get("output1", []):
                qty = float(item.get("hldg_qty", 0))
                if qty == 0:
                    continue
                net_side = "long" if qty > 0 else "short"
                positions.append(FuturesPosition(
                    symbol=item.get("pdno", ""),
                    quantity=abs(qty),
                    avg_price=float(item.get("pchs_avg_pric", 0)),
                    current_price=float(item.get("prpr", 0)),
                    unrealized_pnl=float(item.get("evlu_pfls_amt", 0)),
                    unrealized_pnl_pct=float(item.get("evlu_pfls_rt", 0)),
                    market=Market.KR_FUTURES,
                    currency="KRW",
                    multiplier=250_000,
                    margin_required=float(item.get("mgna_amt", 0)),
                    expiry=item.get("expr_dt", "")[:6] or None,
                    net_side=net_side,
                    pnl_per_contract=float(item.get("evlu_pfls_amt", 0)),
                ))

            logger.debug("kis_futures_positions_fetched", count=len(positions))
            return positions
        except Exception:
            logger.exception("kis_get_futures_positions_failed")
            return []

    async def get_futures_quote(self, symbol: str) -> dict:
        """선물 현재가 조회.

        실계좌: FHKIF03010100 (선물 현재가 조회)
        모의투자: FHKIF03010100은 paper 서버 미지원 → KOSPI200 지수(FHPUP02100000)로
                  근사치 사용 (basis 무시, 모의투자용으로 허용)
        """
        from agentic_capital.adapters.kis_session import _REAL_BASE
        await self._session.ensure_token()
        try:
            r = await self._session.get(
                f"{_REAL_BASE}/uapi/domestic-futureoption/v1/quotations/inquire-price",
                headers=self._session.headers("FHKIF03010100"),
                params={"FID_COND_MRKT_DIV_CODE": "F", "FID_INPUT_ISCD": symbol},
            )
            data = r.json()
            if data.get("rt_cd") == "0":
                output = data.get("output", {})
                price = float(output.get("stck_prpr", 0))
                if price > 0:
                    return {
                        "symbol": symbol,
                        "price": price,
                        "open": float(output.get("stck_oprc", 0)),
                        "high": float(output.get("stck_hgpr", 0)),
                        "low": float(output.get("stck_lwpr", 0)),
                        "volume": int(output.get("acml_vol", 0)),
                        "change": float(output.get("prdy_vrss", 0)),
                        "change_pct": float(output.get("prdy_ctrt", 0)),
                    }
            logger.debug(
                "kis_futures_quote_real_failed",
                symbol=symbol, rt_cd=data.get("rt_cd"), msg=data.get("msg1"),
            )
        except Exception:
            logger.exception("kis_get_futures_quote_failed", symbol=symbol)

        # Fallback: KOSPI200 지수 현재가 (모의투자 또는 실API 장외 시간)
        return await self._get_kospi200_index_as_futures_proxy(symbol)

    async def _get_kospi200_index_as_futures_proxy(self, symbol: str) -> dict:
        """KOSPI200 지수 현재가를 선물 근사치로 반환 (모의투자 전용).

        KIS paper token은 실서버 시세 접근 불가 → Yahoo Finance 공개 API 사용.
        선물 가격 ≈ 지수 가격 (basis 무시 — 모의투자용으로 허용).
        """
        d = await _fetch_yfinance_kospi200()
        if not d:
            return {}
        logger.debug("yfinance_kospi200_price", price=d["price"], symbol=symbol)
        return {"symbol": symbol, **d}

    async def get_active_futures_contracts(self) -> list[dict]:
        """활성 KR 선물 계약 목록 조회.

        KIS는 선물 심볼 목록 전용 API가 없으므로 표준 종목코드 체계로 후보를
        계산하고 get_futures_quote 로 유효성을 검증한다.

        종목코드 체계:
          - KOSPI200 표준: 101 + 월코드 + 연도 마지막 자리  (승수 250,000)
          - KOSPI200 미니: 105 + 월코드 + 연도 마지막 자리  (승수 50,000)
          - 분기월: 3월(C) / 6월(F) / 9월(I) / 12월(L)
          - 만기일: 각 분기 두 번째 목요일

        Returns list[{symbol, price, volume, change_pct, expiry, multiplier}]
        """
        from datetime import date, timedelta

        MONTH_CODES = {3: "C", 6: "F", 9: "I", 12: "L"}
        QUARTERLY = [3, 6, 9, 12]
        today = date.today()

        def _nth_thursday(year: int, month: int, n: int) -> date:
            d = date(year, month, 1)
            days_to_thu = (3 - d.weekday()) % 7  # 3 = Thursday
            return d + timedelta(days=days_to_thu) + timedelta(weeks=n - 1)

        # Enumerate candidates: 2 standard + 2 mini nearest quarterly contracts
        candidates: list[tuple[str, date, int]] = []  # (symbol, expiry, multiplier)
        for y in (today.year, today.year + 1):
            for qm in QUARTERLY:
                expiry = _nth_thursday(y, qm, 2)
                if expiry < today:
                    continue
                code = MONTH_CODES[qm]
                ydigit = str(y)[-1]
                candidates.append((f"101{code}{ydigit}", expiry, 250_000))
                candidates.append((f"105{code}{ydigit}", expiry, 50_000))
            if len(candidates) >= 6:
                break

        results = []
        for sym, exp, mult in candidates[:6]:
            q = await self.get_futures_quote(sym)
            if q and q.get("price", 0) > 0:
                results.append({
                    "symbol": sym,
                    "price": q["price"],
                    "volume": q.get("volume", 0),
                    "change_pct": q.get("change_pct", 0),
                    "expiry": exp.strftime("%Y%m"),
                    "multiplier": mult,
                })

        logger.debug("kis_active_futures_contracts", count=len(results))
        return results

    # ── Order submission ──────────────────────────────────────────────────────

    async def submit_order(self, order: Order) -> OrderResult:
        """Submit an order — routes to correct endpoint based on order.market."""
        if order.market == Market.KR_STOCK:
            return await self._submit_domestic_order(order)
        elif order.market in _OVERSEAS_MARKETS:
            return await self._submit_overseas_order(order)
        elif order.market in _FUTURES_MARKETS:
            return await self._submit_futures_order(order)
        else:
            raise ValueError(f"Unsupported market: {order.market}")

    async def _submit_domestic_order(self, order: Order) -> OrderResult:
        """국내주식 주문 (현금)."""
        await self._session.ensure_token()
        action = "order_buy" if order.side == OrderSide.BUY else "order_sell"
        try:
            body = {
                "CANO": self._session.cano,
                "ACNT_PRDT_CD": self._session.prdt_cd,
                "PDNO": order.symbol,
                "ORD_DVSN": "00" if order.price else "01",  # 00=지정가, 01=시장가
                "ORD_QTY": str(int(order.quantity)),
                "ORD_UNPR": str(int(order.price)) if order.price else "0",
            }
            r = await self._session.post(
                f"{self._session.base_url}/uapi/domestic-stock/v1/trading/order-cash",
                headers=self._session.headers(self._kr_tr(action)),
                json=body,
            )
            data = r.json()

            if data.get("rt_cd") != "0":
                logger.warning(
                    "kis_order_rejected",
                    symbol=order.symbol,
                    msg=data.get("msg1", ""),
                    msg_cd=data.get("msg_cd", ""),
                    rt_cd=data.get("rt_cd", ""),
                    price=order.price,
                    quantity=order.quantity,
                    ord_dvsn=body["ORD_DVSN"],
                )
                return OrderResult(
                    order_id="", symbol=order.symbol, side=order.side,
                    quantity=0.0, filled_price=0.0, status="rejected", market=order.market,
                )

            output = data.get("output", {})
            order_id = output.get("ODNO", "")
            logger.info("kis_domestic_order_submitted", order_id=order_id,
                        symbol=order.symbol, side=order.side.value, quantity=order.quantity)
            return OrderResult(
                order_id=order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                filled_price=order.price or 0.0,
                status="submitted",
                market=order.market,
                metadata={
                    "KRX_FWDG_ORD_ORGNO": output.get("KRX_FWDG_ORD_ORGNO", ""),
                    "ORD_TMD": output.get("ORD_TMD", ""),
                },
            )
        except Exception:
            logger.exception("kis_submit_domestic_order_failed", symbol=order.symbol)
            raise

    async def _submit_overseas_order(self, order: Order) -> OrderResult:
        """해외주식 주문 (real mode only)."""
        self._assert_real_for_overseas()
        await self._session.ensure_token()
        excg_cd = _exchange_code(order)
        tr_id = _OVS_TR["order_buy"] if order.side == OrderSide.BUY else _OVS_TR["order_sell"]
        try:
            body = {
                "CANO": self._session.cano,
                "ACNT_PRDT_CD": self._session.prdt_cd,
                "OVRS_EXCG_CD": excg_cd,
                "PDNO": order.symbol,
                "ORD_DVSN": "00" if order.price else "00",   # overseas: 00=지정가 (시장가 없음)
                "ORD_QTY": str(int(order.quantity)),
                "OVRS_ORD_UNPR": str(order.price or 0),
            }
            r = await self._session.post(
                f"{self._session.base_url}/uapi/overseas-stock/v1/trading/order",
                headers=self._session.headers(tr_id),
                json=body,
            )
            data = r.json()

            if data.get("rt_cd") != "0":
                logger.warning("kis_overseas_order_rejected",
                               symbol=order.symbol, exchange=excg_cd, msg=data.get("msg1", ""))
                return OrderResult(
                    order_id="", symbol=order.symbol, side=order.side,
                    quantity=0.0, filled_price=0.0, status="rejected", market=order.market,
                )

            output = data.get("output", {})
            order_id = output.get("ODNO", "")
            logger.info("kis_overseas_order_submitted", order_id=order_id,
                        symbol=order.symbol, exchange=excg_cd, side=order.side.value,
                        quantity=order.quantity)
            return OrderResult(
                order_id=order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                filled_price=order.price or 0.0,
                status="submitted",
                market=order.market,
                metadata={
                    "exchange": excg_cd,
                    "KRX_FWDG_ORD_ORGNO": output.get("KRX_FWDG_ORD_ORGNO", ""),
                },
            )
        except Exception:
            logger.exception("kis_submit_overseas_order_failed", symbol=order.symbol, exchange=excg_cd)
            raise

    async def _submit_futures_order(self, order: Order) -> OrderResult:
        """국내선물/옵션 주문."""
        await self._session.ensure_token()
        action = "order_buy" if order.side == OrderSide.BUY else "order_sell"
        try:
            body = {
                "CANO": self._session.cano,
                "ACNT_PRDT_CD": self._session.prdt_cd,
                "PDNO": order.symbol,
                "ORD_DVSN": "01" if not order.price else "00",  # 01=시장가, 00=지정가
                "ORD_QTY": str(int(order.quantity)),
                "ORD_UNPR": str(order.price or 0),
                # 01=신규(open), 02=청산(close) — must be explicit, not inferred from side
                "CBLC_DVSN": "02" if order.position_effect == "close" else "01",
            }
            r = await self._session.post(
                f"{self._session.base_url}/uapi/domestic-futureoption/v1/trading/order",
                headers=self._session.headers(self._fut_tr(action)),
                json=body,
            )
            data = r.json()

            if data.get("rt_cd") != "0":
                logger.warning("kis_futures_order_rejected",
                               symbol=order.symbol, msg=data.get("msg1", ""),
                               rt_cd=data.get("rt_cd"),
                               msg_cd=data.get("msg_cd"),
                               body_sent=body)
                return OrderResult(
                    order_id="", symbol=order.symbol, side=order.side,
                    quantity=0.0, filled_price=0.0, status="rejected", market=order.market,
                )

            output = data.get("output", {})
            order_id = output.get("ODNO", "")
            logger.info("kis_futures_order_submitted", order_id=order_id,
                        symbol=order.symbol, side=order.side.value)
            return OrderResult(
                order_id=order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                filled_price=order.price or 0.0,
                status="submitted",
                market=order.market,
                metadata={"KRX_FWDG_ORD_ORGNO": output.get("KRX_FWDG_ORD_ORGNO", "")},
            )
        except Exception:
            logger.exception("kis_submit_futures_order_failed", symbol=order.symbol)
            raise

    # ── Order management ──────────────────────────────────────────────────────

    async def get_order_status(self, order_id: str) -> OrderResult:
        """Get order status via fill inquiry (국내주식)."""
        await self._session.ensure_token()
        try:
            today = datetime.now().strftime("%Y%m%d")
            r = await self._session.get(
                f"{self._session.base_url}/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
                headers=self._session.headers(self._kr_tr("fills")),
                params={
                    "CANO": self._session.cano,
                    "ACNT_PRDT_CD": self._session.prdt_cd,
                    "INQR_STRT_DT": today,
                    "INQR_END_DT": today,
                    "SLL_BUY_DVSN_CD": "00",    # 00=전체
                    "INQR_DVSN": "00",
                    "PDNO": "",
                    "CCL_DVSN": "00",            # 00=전체
                    "ORD_GNO_BRNO": "",
                    "ODNO": order_id,
                    "INQR_DVSN_3": "00",
                    "INQR_DVSN_1": "",
                    "CTX_AREA_FK100": "",
                    "CTX_AREA_NK100": "",
                },
            )
            data = r.json()
            if data.get("rt_cd") != "0":
                logger.warning("kis_order_status_failed", order_id=order_id, msg=data.get("msg1", ""))
                return OrderResult(
                    order_id=order_id, symbol="", side=OrderSide.BUY,
                    quantity=0.0, filled_price=0.0, status="unknown",
                )

            items = data.get("output1", [])
            for item in items:
                if item.get("odno") == order_id or item.get("orgn_odno") == order_id:
                    ccld_qty = float(item.get("tot_ccld_qty", 0))
                    ord_qty = float(item.get("ord_qty", 0))
                    status = "filled" if ccld_qty >= ord_qty and ord_qty > 0 else (
                        "partial" if ccld_qty > 0 else "open"
                    )
                    side_cd = item.get("sll_buy_dvsn_cd", "02")
                    return OrderResult(
                        order_id=order_id,
                        symbol=item.get("pdno", ""),
                        side=OrderSide.BUY if side_cd == "02" else OrderSide.SELL,
                        quantity=ccld_qty,
                        filled_price=float(item.get("avg_prvs", 0)),
                        status=status,
                    )

            logger.debug("kis_order_status_not_found", order_id=order_id)
            return OrderResult(
                order_id=order_id, symbol="", side=OrderSide.BUY,
                quantity=0.0, filled_price=0.0, status="unknown",
            )
        except Exception:
            logger.exception("kis_get_order_status_failed", order_id=order_id)
            raise

    async def cancel_order(self, order_id: str, **kwargs: Any) -> bool:
        """Cancel a domestic stock order.

        Args:
            order_id: Original order number (ODNO from submit_order).
            **kwargs:
                krx_org_no: KRX_FWDG_ORD_ORGNO from submit_order metadata (required for live).
                symbol: Stock code (optional, improves reliability).

        Returns:
            True if cancellation was accepted.
        """
        await self._session.ensure_token()
        krx_org_no = kwargs.get("krx_org_no", "")
        try:
            body = {
                "CANO": self._session.cano,
                "ACNT_PRDT_CD": self._session.prdt_cd,
                "KRX_FWDG_ORD_ORGNO": krx_org_no,
                "ORGN_ODNO": order_id,
                "ORD_DVSN": "00",
                "RVSE_CNCL_DVSN_CD": "02",      # 02 = 취소
                "ORD_QTY": "0",
                "ORD_UNPR": "0",
                "QTY_ALL_ORD_YN": "Y",           # cancel all remaining quantity
            }
            r = await self._session.post(
                f"{self._session.base_url}/uapi/domestic-stock/v1/trading/order-rvsecncl",
                headers=self._session.headers(self._kr_tr("order_cancel")),
                json=body,
            )
            data = r.json()
            if data.get("rt_cd") != "0":
                logger.warning("kis_cancel_failed", order_id=order_id, msg=data.get("msg1", ""))
                return False
            logger.info("kis_order_cancelled", order_id=order_id)
            return True
        except Exception:
            logger.exception("kis_cancel_order_failed", order_id=order_id)
            raise

    async def cancel_overseas_order(self, order_id: str, exchange: str, symbol: str) -> bool:
        """Cancel an overseas stock order (real mode only).

        Args:
            order_id: Original order number (ODNO).
            exchange: Exchange code (e.g., "NASD", "NYSE").
            symbol: Stock symbol.
        """
        self._assert_real_for_overseas()
        await self._session.ensure_token()
        try:
            body = {
                "CANO": self._session.cano,
                "ACNT_PRDT_CD": self._session.prdt_cd,
                "OVRS_EXCG_CD": exchange,
                "PDNO": symbol,
                "ORGN_ODNO": order_id,
                "ORD_SVR_DVSN_CD": "0",
                "RVSE_CNCL_DVSN_CD": "02",      # 02 = 취소
                "ORD_QTY": "0",
                "OVRS_ORD_UNPR": "0",
                "CTG_NO": "",
                "ORD_QTY2": "0",
            }
            r = await self._session.post(
                f"{self._session.base_url}/uapi/overseas-stock/v1/trading/order-rvsecncl",
                headers=self._session.headers(_OVS_TR["order_cancel"]),
                json=body,
            )
            data = r.json()
            if data.get("rt_cd") != "0":
                logger.warning("kis_overseas_cancel_failed", order_id=order_id,
                               msg=data.get("msg1", ""))
                return False
            logger.info("kis_overseas_order_cancelled", order_id=order_id, exchange=exchange)
            return True
        except Exception:
            logger.exception("kis_cancel_overseas_order_failed", order_id=order_id)
            raise

    # ── Fill history ──────────────────────────────────────────────────────────

    async def get_fills(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        symbol: str = "",
    ) -> list[OrderResult]:
        """Get domestic stock order fill history.

        Args:
            start_date: YYYYMMDD format. Defaults to today.
            end_date: YYYYMMDD format. Defaults to today.
            symbol: Filter by stock code (empty = all).

        Returns:
            List of filled orders.
        """
        await self._session.ensure_token()
        today = datetime.now().strftime("%Y%m%d")
        start = start_date or today
        end = end_date or today
        try:
            r = await self._session.get(
                f"{self._session.base_url}/uapi/domestic-stock/v1/trading/inquire-daily-ccld",
                headers=self._session.headers(self._kr_tr("fills")),
                params={
                    "CANO": self._session.cano,
                    "ACNT_PRDT_CD": self._session.prdt_cd,
                    "INQR_STRT_DT": start,
                    "INQR_END_DT": end,
                    "SLL_BUY_DVSN_CD": "00",
                    "INQR_DVSN": "00",
                    "PDNO": symbol,
                    "CCL_DVSN": "01",           # 01=체결만
                    "ORD_GNO_BRNO": "",
                    "ODNO": "",
                    "INQR_DVSN_3": "00",
                    "INQR_DVSN_1": "",
                    "CTX_AREA_FK100": "",
                    "CTX_AREA_NK100": "",
                },
            )
            data = r.json()
            if data.get("rt_cd") != "0":
                raise RuntimeError(f"KIS fills failed: {data.get('msg1', data)}")

            fills = []
            for item in data.get("output1", []):
                ccld_qty = float(item.get("tot_ccld_qty", 0))
                if ccld_qty <= 0:
                    continue
                side_cd = item.get("sll_buy_dvsn_cd", "02")
                fills.append(OrderResult(
                    order_id=item.get("odno", ""),
                    symbol=item.get("pdno", ""),
                    side=OrderSide.BUY if side_cd == "02" else OrderSide.SELL,
                    quantity=ccld_qty,
                    filled_price=float(item.get("avg_prvs", 0)),
                    status="filled",
                    market=Market.KR_STOCK,
                    metadata={
                        "order_time": item.get("ord_tmm", ""),
                        "fill_time": item.get("ccld_dtime", ""),
                        "item_name": item.get("prdt_name", ""),
                    },
                ))

            logger.debug("kis_fills_fetched", count=len(fills), start=start, end=end)
            return fills
        except Exception:
            logger.exception("kis_get_fills_failed")
            raise

    async def get_overseas_fills(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[OrderResult]:
        """Get overseas stock order fill history (real mode only).

        Args:
            start_date: YYYYMMDD format. Defaults to today.
            end_date: YYYYMMDD format. Defaults to today.
        """
        self._assert_real_for_overseas()
        await self._session.ensure_token()
        today = datetime.now().strftime("%Y%m%d")
        start = start_date or today
        end = end_date or today
        try:
            r = await self._session.get(
                f"{self._session.base_url}/uapi/overseas-stock/v1/trading/inquire-ccnl",
                headers=self._session.headers(_OVS_TR["fills"]),
                params={
                    "CANO": self._session.cano,
                    "ACNT_PRDT_CD": self._session.prdt_cd,
                    "PDNO": "",
                    "ORD_STRT_DT": start,
                    "ORD_END_DT": end,
                    "SLL_BUY_DVSN": "00",
                    "CCLD_NCCS_DVSN": "01",     # 01=체결
                    "OVRS_EXCG_CD": "",
                    "SORT_SQN": "DS",
                    "ORD_DT": "",
                    "ORD_GNO_BRNO": "",
                    "ODNO": "",
                    "CTX_AREA_NK200": "",
                    "CTX_AREA_FK200": "",
                },
            )
            data = r.json()
            if data.get("rt_cd") != "0":
                raise RuntimeError(f"KIS overseas fills failed: {data.get('msg1', data)}")

            excg_to_market = {
                "NASD": Market.US_STOCK, "NYSE": Market.US_STOCK, "AMEX": Market.US_STOCK,
                "SEHK": Market.HK_STOCK,
                "SHAA": Market.CN_STOCK, "SZAA": Market.CN_STOCK,
                "TKSE": Market.JP_STOCK,
                "HASE": Market.VN_STOCK, "VNSE": Market.VN_STOCK,
            }

            fills = []
            for item in data.get("output1", []):
                ccld_qty = float(item.get("ft_ccld_qty", 0))
                if ccld_qty <= 0:
                    continue
                excg_cd = item.get("ovrs_excg_cd", "")
                side_cd = item.get("sll_buy_dvsn_cd", "02")
                fills.append(OrderResult(
                    order_id=item.get("odno", ""),
                    symbol=item.get("pdno", ""),
                    side=OrderSide.BUY if side_cd == "02" else OrderSide.SELL,
                    quantity=ccld_qty,
                    filled_price=float(item.get("ft_ccld_unpr3", 0)),
                    status="filled",
                    market=excg_to_market.get(excg_cd, Market.US_STOCK),
                    metadata={"exchange": excg_cd, "currency": item.get("tr_crcy_cd", "USD")},
                ))

            logger.debug("kis_overseas_fills_fetched", count=len(fills))
            return fills
        except Exception:
            logger.exception("kis_get_overseas_fills_failed")
            raise

