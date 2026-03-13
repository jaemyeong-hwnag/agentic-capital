"""KIS WebSocket adapter — real-time price and order book subscriptions.

Agents subscribe/unsubscribe to symbols freely. System delivers ticks via callback.
Paper trading only supports domestic; overseas requires real account.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from typing import Any

import structlog

from agentic_capital.adapters.kis_session import KISSession

logger = structlog.get_logger()

# TR IDs for WebSocket subscriptions
_TR_DOMESTIC_PRICE = "H0STCNT0"    # 국내주식 체결가 (real-time trade price)
_TR_DOMESTIC_ASK = "H0STASP0"      # 국내주식 호가 (real-time order book)
_TR_OVERSEAS_PRICE = "HDFSCNT0"    # 해외주식 체결가 (real-time overseas price)

TickCallback = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class KISWebSocketAdapter:
    """Real-time market data via KIS WebSocket.

    Usage:
        ws = KISWebSocketAdapter(session=session)
        await ws.connect()
        await ws.subscribe_price("005930", callback=my_handler)
        await ws.subscribe_overseas_price("AAPL", exchange="NASD", callback=my_handler)
        # ... agent runs ...
        await ws.unsubscribe_price("005930")
        await ws.disconnect()
    """

    def __init__(self, *, session: KISSession | None = None) -> None:
        if session is None:
            session = KISSession()
        self._session = session
        self._ws = None
        self._listen_task: asyncio.Task | None = None
        self._callbacks: dict[str, TickCallback] = {}  # tr_key → callback
        self._connected = False

        # WebSocket URL: paper = :31000, real = :21000
        if session.is_paper:
            self._ws_url = "wss://openapivts.koreainvestment.com:31000/websocket"
        else:
            self._ws_url = "wss://ops.koreainvestment.com:21000/websocket"

        logger.info("kis_websocket_initialized", mode="paper" if session.is_paper else "live")

    async def connect(self) -> None:
        """Open WebSocket connection and start listener loop."""
        try:
            import websockets
        except ImportError:
            raise ImportError("websockets package required: pip install websockets")

        approval_key = await self._get_approval_key()
        self._approval_key = approval_key

        self._ws = await websockets.connect(self._ws_url)
        self._connected = True
        self._listen_task = asyncio.create_task(self._listen_loop())
        logger.info("kis_websocket_connected", url=self._ws_url)

    async def disconnect(self) -> None:
        """Close WebSocket and stop listener."""
        self._connected = False
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
        logger.info("kis_websocket_disconnected")

    async def subscribe_price(self, symbol: str, callback: TickCallback) -> None:
        """Subscribe to domestic stock real-time trade price."""
        tr_key = f"{_TR_DOMESTIC_PRICE}|{symbol}"
        self._callbacks[tr_key] = callback
        await self._send_subscribe(_TR_DOMESTIC_PRICE, symbol)
        logger.info("kis_ws_subscribed_price", symbol=symbol)

    async def unsubscribe_price(self, symbol: str) -> None:
        """Unsubscribe from domestic stock real-time price."""
        tr_key = f"{_TR_DOMESTIC_PRICE}|{symbol}"
        self._callbacks.pop(tr_key, None)
        await self._send_unsubscribe(_TR_DOMESTIC_PRICE, symbol)
        logger.info("kis_ws_unsubscribed_price", symbol=symbol)

    async def subscribe_order_book(self, symbol: str, callback: TickCallback) -> None:
        """Subscribe to domestic stock real-time order book."""
        tr_key = f"{_TR_DOMESTIC_ASK}|{symbol}"
        self._callbacks[tr_key] = callback
        await self._send_subscribe(_TR_DOMESTIC_ASK, symbol)
        logger.info("kis_ws_subscribed_orderbook", symbol=symbol)

    async def unsubscribe_order_book(self, symbol: str) -> None:
        """Unsubscribe from domestic stock real-time order book."""
        tr_key = f"{_TR_DOMESTIC_ASK}|{symbol}"
        self._callbacks.pop(tr_key, None)
        await self._send_unsubscribe(_TR_DOMESTIC_ASK, symbol)

    async def subscribe_overseas_price(
        self,
        symbol: str,
        exchange: str,
        callback: TickCallback,
    ) -> None:
        """Subscribe to overseas stock real-time price (real account only)."""
        if self._session.is_paper:
            raise NotImplementedError(
                "KIS paper trading does not support overseas WebSocket. Use real account."
            )
        tr_key = f"{_TR_OVERSEAS_PRICE}|{exchange}_{symbol}"
        self._callbacks[tr_key] = callback
        await self._send_subscribe(_TR_OVERSEAS_PRICE, f"{exchange}_{symbol}")
        logger.info("kis_ws_subscribed_overseas", symbol=symbol, exchange=exchange)

    async def unsubscribe_overseas_price(self, symbol: str, exchange: str) -> None:
        """Unsubscribe from overseas stock real-time price."""
        tr_key = f"{_TR_OVERSEAS_PRICE}|{exchange}_{symbol}"
        self._callbacks.pop(tr_key, None)
        await self._send_unsubscribe(_TR_OVERSEAS_PRICE, f"{exchange}_{symbol}")

    async def _get_approval_key(self) -> str:
        """Get WebSocket approval key from KIS."""
        from agentic_capital.config import settings

        r = await self._session.client.post(
            f"{self._session.base_url}/oauth2/Approval",
            json={
                "grant_type": "client_credentials",
                "appkey": settings.kis_app_key,
                "secretkey": settings.kis_app_secret,
            },
        )
        data = r.json()
        key = data.get("approval_key", "")
        if not key:
            raise RuntimeError(f"KIS WebSocket approval key failed: {data}")
        return key

    async def _send_subscribe(self, tr_id: str, tr_key: str) -> None:
        """Send subscription request."""
        if not self._ws:
            raise RuntimeError("WebSocket not connected. Call connect() first.")
        msg = {
            "header": {
                "approval_key": self._approval_key,
                "custtype": "P",
                "tr_type": "1",   # 1 = subscribe
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": tr_id,
                    "tr_key": tr_key,
                }
            },
        }
        await self._ws.send(json.dumps(msg))

    async def _send_unsubscribe(self, tr_id: str, tr_key: str) -> None:
        """Send unsubscription request."""
        if not self._ws:
            return
        msg = {
            "header": {
                "approval_key": self._approval_key,
                "custtype": "P",
                "tr_type": "2",   # 2 = unsubscribe
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": tr_id,
                    "tr_key": tr_key,
                }
            },
        }
        await self._ws.send(json.dumps(msg))

    async def _listen_loop(self) -> None:
        """Main WebSocket receive loop — dispatches ticks to callbacks."""
        if not self._ws:
            return

        try:
            async for raw_msg in self._ws:
                if not self._connected:
                    break
                await self._handle_message(raw_msg)
        except Exception:
            if self._connected:
                logger.exception("kis_ws_listen_error")

    async def _handle_message(self, raw_msg: str | bytes) -> None:
        """Parse incoming WebSocket message and dispatch to registered callback."""
        try:
            if isinstance(raw_msg, bytes):
                raw_msg = raw_msg.decode("utf-8")

            # KIS sends JSON control messages (subscribe ack, ping/pong)
            # and pipe-delimited data messages
            if raw_msg.startswith("{"):
                data = json.loads(raw_msg)
                header = data.get("header", {})
                if header.get("tr_id") in ("PINGPONG",):
                    await self._ws.send(raw_msg)  # pong
                return

            # Data message: "0|TR_ID|seq|data..."
            parts = raw_msg.split("|", 3)
            if len(parts) < 4:
                return

            recvflag, tr_id, _, body = parts

            tick = _parse_tick(tr_id, body)
            if not tick:
                return

            # Dispatch to all matching callbacks
            for key, cb in list(self._callbacks.items()):
                if key.startswith(tr_id):
                    try:
                        await cb(tick)
                    except Exception:
                        logger.exception("kis_ws_callback_error", tr_id=tr_id)

        except Exception:
            logger.exception("kis_ws_parse_error")


def _parse_tick(tr_id: str, body: str) -> dict[str, Any] | None:
    """Parse pipe-delimited KIS real-time data into a dict."""
    fields = body.split("^")

    if tr_id == _TR_DOMESTIC_PRICE:
        # 국내주식 체결가 fields (선택적)
        if len(fields) < 13:
            return None
        return {
            "type": "trade",
            "market": "kr_stock",
            "symbol": fields[0],
            "timestamp": fields[1],  # HHMMSS
            "price": _safe_float(fields[2]),
            "change": _safe_float(fields[4]),
            "volume": _safe_float(fields[9]),
            "cum_volume": _safe_float(fields[13]) if len(fields) > 13 else None,
        }

    if tr_id == _TR_DOMESTIC_ASK:
        # 국내주식 호가 — best bid/ask
        if len(fields) < 10:
            return None
        return {
            "type": "orderbook",
            "market": "kr_stock",
            "symbol": fields[0],
            "timestamp": fields[1],
            "ask1_price": _safe_float(fields[3]),
            "ask1_qty": _safe_float(fields[23]) if len(fields) > 23 else None,
            "bid1_price": _safe_float(fields[13]),
            "bid1_qty": _safe_float(fields[33]) if len(fields) > 33 else None,
        }

    if tr_id == _TR_OVERSEAS_PRICE:
        if len(fields) < 7:
            return None
        return {
            "type": "trade",
            "market": "overseas",
            "symbol": fields[0],
            "price": _safe_float(fields[2]),
            "volume": _safe_float(fields[6]) if len(fields) > 6 else None,
        }

    return None


def _safe_float(val: str) -> float | None:
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
