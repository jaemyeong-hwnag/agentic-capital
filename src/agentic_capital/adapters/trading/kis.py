"""KIS (한국투자증권) trading adapter — Korean stock trading via Open API."""

from __future__ import annotations

import structlog
import httpx

from agentic_capital.config import settings
from agentic_capital.ports.trading import (
    Balance,
    Order,
    OrderResult,
    OrderSide,
    Position,
    TradingPort,
)

logger = structlog.get_logger()

# KIS API base URLs
_REAL_BASE = "https://openapi.koreainvestment.com:9443"
_PAPER_BASE = "https://openapivts.koreainvestment.com:29443"

# Transaction IDs
_TR_IDS = {
    "balance": {"real": "TTTC8434R", "paper": "VTTC8434R"},
    "order_buy": {"real": "TTTC0802U", "paper": "VTTC0802U"},
    "order_sell": {"real": "TTTC0801U", "paper": "VTTC0801U"},
    "price": {"real": "FHKST01010100", "paper": "FHKST01010100"},
}


class KISTradingAdapter(TradingPort):
    """KIS Open API adapter for Korean stock trading.

    Supports both paper trading (모의투자) and live trading (실전투자).
    """

    def __init__(
        self,
        *,
        app_key: str = "",
        app_secret: str = "",
        account_no: str = "",
        is_paper: bool | None = None,
    ) -> None:
        self._app_key = app_key or settings.kis_app_key
        self._app_secret = app_secret or settings.kis_app_secret
        self._account_no = account_no or settings.kis_account_no
        self._is_paper = is_paper if is_paper is not None else settings.kis_is_paper

        if not all([self._app_key, self._app_secret, self._account_no]):
            raise ValueError("KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO are required")

        self._base_url = _PAPER_BASE if self._is_paper else _REAL_BASE
        self._cano = self._account_no[:8]
        self._prdt_cd = self._account_no[8:]
        self._access_token: str | None = None
        self._client = httpx.AsyncClient(timeout=15.0)

        mode = "paper" if self._is_paper else "LIVE"
        logger.info("kis_adapter_initialized", mode=mode, account=self._account_no)

    def _tr_id(self, action: str) -> str:
        mode = "paper" if self._is_paper else "real"
        return _TR_IDS[action][mode]

    async def _ensure_token(self) -> str:
        """Get or refresh access token."""
        if self._access_token:
            return self._access_token

        try:
            r = await self._client.post(
                f"{self._base_url}/oauth2/tokenP",
                json={
                    "grant_type": "client_credentials",
                    "appkey": self._app_key,
                    "appsecret": self._app_secret,
                },
            )
            data = r.json()
            if "access_token" not in data:
                raise RuntimeError(f"KIS token failed: {data}")
            self._access_token = data["access_token"]
            logger.info("kis_token_acquired")
            return self._access_token
        except Exception:
            logger.exception("kis_token_failed")
            raise

    def _headers(self, tr_id: str) -> dict[str, str]:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._access_token}",
            "appkey": self._app_key,
            "appsecret": self._app_secret,
            "tr_id": tr_id,
        }

    async def get_balance(self) -> Balance:
        """Get account balance from KIS."""
        token = await self._ensure_token()
        try:
            r = await self._client.get(
                f"{self._base_url}/uapi/domestic-stock/v1/trading/inquire-balance",
                headers=self._headers(self._tr_id("balance")),
                params={
                    "CANO": self._cano,
                    "ACNT_PRDT_CD": self._prdt_cd,
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
            total = float(info.get("tot_evlu_amt", 0))
            available = float(info.get("dnca_tot_amt", 0))

            logger.debug("kis_balance_fetched", total=total, available=available)
            return Balance(total=total, available=available, currency="KRW")
        except Exception:
            logger.exception("kis_get_balance_failed")
            raise

    async def get_positions(self) -> list[Position]:
        """Get current stock positions from KIS."""
        token = await self._ensure_token()
        try:
            r = await self._client.get(
                f"{self._base_url}/uapi/domestic-stock/v1/trading/inquire-balance",
                headers=self._headers(self._tr_id("balance")),
                params={
                    "CANO": self._cano,
                    "ACNT_PRDT_CD": self._prdt_cd,
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
                avg_price = float(item.get("pchs_avg_pric", 0))
                current_price = float(item.get("prpr", 0))
                pnl = float(item.get("evlu_pfls_amt", 0))
                pnl_pct = float(item.get("evlu_pfls_rt", 0))

                positions.append(Position(
                    symbol=item.get("pdno", ""),
                    quantity=qty,
                    avg_price=avg_price,
                    current_price=current_price,
                    unrealized_pnl=pnl,
                    unrealized_pnl_pct=pnl_pct,
                ))

            logger.debug("kis_positions_fetched", count=len(positions))
            return positions
        except Exception:
            logger.exception("kis_get_positions_failed")
            raise

    async def submit_order(self, order: Order) -> OrderResult:
        """Submit a stock order to KIS."""
        token = await self._ensure_token()
        action = "order_buy" if order.side == OrderSide.BUY else "order_sell"

        try:
            body = {
                "CANO": self._cano,
                "ACNT_PRDT_CD": self._prdt_cd,
                "PDNO": order.symbol,
                "ORD_DVSN": "00" if order.price else "01",  # 00=지정가, 01=시장가
                "ORD_QTY": str(int(order.quantity)),
                "ORD_UNPR": str(int(order.price)) if order.price else "0",
            }
            r = await self._client.post(
                f"{self._base_url}/uapi/domestic-stock/v1/trading/order-cash",
                headers=self._headers(self._tr_id(action)),
                json=body,
            )
            data = r.json()

            if data.get("rt_cd") != "0":
                logger.warning(
                    "kis_order_rejected",
                    symbol=order.symbol,
                    side=order.side.value,
                    msg=data.get("msg1", ""),
                )
                return OrderResult(
                    order_id="",
                    symbol=order.symbol,
                    side=order.side,
                    quantity=0.0,
                    filled_price=0.0,
                    status="rejected",
                )

            output = data.get("output", {})
            order_id = output.get("ODNO", "")
            logger.info(
                "kis_order_submitted",
                order_id=order_id,
                symbol=order.symbol,
                side=order.side.value,
                quantity=order.quantity,
            )
            return OrderResult(
                order_id=order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                filled_price=order.price or 0.0,
                status="submitted",
            )
        except Exception:
            logger.exception(
                "kis_submit_order_failed",
                symbol=order.symbol,
                side=order.side.value,
            )
            raise

    async def get_order_status(self, order_id: str) -> OrderResult:
        """Get order status — KIS doesn't have single-order query, returns placeholder."""
        logger.debug("kis_order_status_query", order_id=order_id)
        return OrderResult(
            order_id=order_id,
            symbol="",
            side=OrderSide.BUY,
            quantity=0.0,
            filled_price=0.0,
            status="unknown",
        )

    async def get_quote(self, symbol: str) -> dict:
        """Get current price quote for a Korean stock symbol."""
        token = await self._ensure_token()
        try:
            r = await self._client.get(
                f"{self._base_url}/uapi/domestic-stock/v1/quotations/inquire-price",
                headers=self._headers(self._tr_id("price")),
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": symbol,
                },
            )
            data = r.json()
            if data.get("rt_cd") != "0":
                raise RuntimeError(f"KIS quote failed: {data.get('msg1', data)}")

            output = data.get("output", {})
            logger.debug("kis_quote_fetched", symbol=symbol, price=output.get("stck_prpr"))
            return {
                "symbol": symbol,
                "price": int(output.get("stck_prpr", 0)),
                "change": int(output.get("prdy_vrss", 0)),
                "change_pct": float(output.get("prdy_ctrt", 0)),
                "volume": int(output.get("acml_vol", 0)),
            }
        except Exception:
            logger.exception("kis_get_quote_failed", symbol=symbol)
            raise
