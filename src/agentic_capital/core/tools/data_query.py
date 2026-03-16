"""Agent tools — account/position queries, market data, and order execution.

System provides: account queries, market data (quote/ohlcv), and trading.
No methodology constraints. No trading restrictions. Only limit: available capital.
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Input schemas for structured tool calling
# ---------------------------------------------------------------------------


class GetFillsInput(BaseModel):
    start_date: str | None = Field(default=None, description="Start date YYYYMMDD")
    end_date: str | None = Field(default=None, description="End date YYYYMMDD")
    symbol: str = Field(default="", description="Filter by symbol (empty = all)")


class SubmitOrderInput(BaseModel):
    symbol: str = Field(description="Ticker symbol to trade")
    side: str = Field(description="Trade direction: buy | sell")
    quantity: float = Field(description="Number of shares/units")
    price: float | None = Field(default=None, description="Limit price (omit for market order)")
    market: str = Field(description="Market you choose: kr_stock (KRX stocks+ETFs+leverage ETFs) | us_stock (NYSE/NASDAQ stocks+ETFs+leveraged ETFs) | kr_futures | kr_options | hk_stock | cn_stock | jp_stock | vn_stock")
    exchange: str | None = Field(default=None, description="Exchange code for overseas (NASD|NYSE|AMEX|SEHK|SHAA|TKSE|HASE)")


class CancelOrderInput(BaseModel):
    order_id: str = Field(description="Order ID to cancel")
    market: str = Field(description="Market: kr_stock | us_stock | kr_futures | kr_options | hk_stock | cn_stock | jp_stock | vn_stock")
    symbol: str = Field(default="", description="Symbol (required for some exchanges)")
    quantity: float = Field(default=0.0, description="Quantity (required for KIS cancel)")


class SaveMemoryInput(BaseModel):
    content: str = Field(description="Memory content to save")
    keywords: list[str] = Field(default_factory=list, description="Keywords for search")


class SearchMemoryInput(BaseModel):
    query: str = Field(description="Search query")
    limit: int = Field(default=5, description="Max results")


class SendMessageInput(BaseModel):
    to_agent: str = Field(description="Target agent name or ID")
    type: str = Field(default="SIG", description="SIG|INSTR|RPT|QRY|ACK|ERR")
    content: str = Field(default="", description="Compact k:v payload e.g. sym:005930,act:BUY,cf:0.87,why:RSI_OS")


class RequestWakeupInput(BaseModel):
    seconds: int = Field(description="Seconds until next cycle. 0=immediately, 3600=1h, 86400=1d")


class GetQuoteInput(BaseModel):
    symbol: str = Field(description="Symbol to quote. KR stocks: 6-digit code (e.g. 005930). US: ticker (e.g. AAPL)")


class GetOHLCVInput(BaseModel):
    symbol: str = Field(description="Symbol. KR: 6-digit code. US: ticker.")
    timeframe: str = Field(default="1d", description="Candle size: 1m|5m|15m|60m|1d|1w|1mo|3mo")
    limit: int = Field(default=20, description="Number of candles to return (max 100)")


# ---------------------------------------------------------------------------
# Tool builder — creates bound tools for a given agent cycle
# ---------------------------------------------------------------------------


def build_agent_tools(
    *,
    trading: Any = None,
    market_data: Any = None,
    recorder: Any = None,
    agent_id: str = "",
    agent_name: str = "",
    agent_memory: dict | None = None,
    agents_registry: dict | None = None,  # name → agent_id
) -> tuple:
    """Build LangChain StructuredTools bound to the given adapters.

    Provides: account queries, market data (quote/ohlcv), trading, messaging.
    Returns (tools, decisions_sink, messages_sink, wakeup_sink).
    """
    memory = agent_memory if agent_memory is not None else {}
    decisions_sink: list[dict] = []   # collects all decisions for recording
    messages_sink: list[dict] = []    # collects outbound messages
    wakeup_sink: list[int] = []       # agent-requested next cycle delay (seconds)

    # ---- Account query tools (compact AI-to-AI format) -------------------

    async def get_balance() -> str:
        """Get current account balance (total equity, available cash, currency)."""
        if not trading:
            return "ERR:no_trading"
        try:
            from agentic_capital.formats.compact import bal as _bal
            b = await trading.get_balance()
            return _bal(b.total, b.available, b.currency)
        except Exception as e:
            return f"ERR:{e}"

    async def get_positions() -> str:
        """Get all open positions with quantity, avg price, unrealized P&L."""
        if not trading:
            return "@pos[0](sym,qty,avg,cur,pnl,pct,mkt,ccy)"
        try:
            from agentic_capital.formats.compact import pos as _pos
            positions = await trading.get_positions()
            return _pos([
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_price": p.avg_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "unrealized_pnl_pct": p.unrealized_pnl_pct,
                    "market": p.market,
                    "currency": p.currency,
                }
                for p in positions
            ])
        except Exception as e:
            return f"ERR:{e}"

    async def get_fills(
        start_date: str | None = None,
        end_date: str | None = None,
        symbol: str = "",
    ) -> str:
        """Get order fill history."""
        if not trading:
            return "@fills[0](oid,sym,sd,qty,px,st)"
        try:
            from agentic_capital.formats.compact import fills as _fills
            fill_list = await trading.get_fills(start_date=start_date, end_date=end_date, symbol=symbol)
            return _fills([
                {
                    "order_id": f.order_id,
                    "symbol": f.symbol,
                    "side": f.side,
                    "quantity": f.quantity,
                    "filled_price": f.filled_price,
                    "status": f.status,
                }
                for f in fill_list
            ])
        except Exception as e:
            return f"ERR:{e}"

    # ---- Trading tools ---------------------------------------------------

    async def submit_order(
        symbol: str,
        side: str,
        quantity: float,
        market: str,
        price: float | None = None,
        exchange: str | None = None,
    ) -> str:
        """Submit a buy or sell order. Returns compact order result."""
        if not trading:
            return "ERR:no_trading"
        try:
            from agentic_capital.formats.compact import order as _order
            from agentic_capital.ports.trading import Market, Order, OrderSide, OrderType

            o = Order(
                symbol=symbol,
                side=OrderSide(side.lower()),
                order_type=OrderType.LIMIT if price is not None else OrderType.MARKET,
                quantity=quantity,
                price=price,
                market=Market(market),
                exchange=exchange,
            )
            result = await trading.submit_order(o)

            # For market orders KIS paper API returns filled_price=0.
            # Fall back to current quote price as best estimate.
            effective_price = price or result.filled_price
            if not effective_price and market_data:
                try:
                    q = await market_data.get_quote(symbol)
                    effective_price = q.price
                except Exception:
                    pass

            from agentic_capital.simulation.recorder import _estimate_commission
            trade_value = effective_price * result.quantity if effective_price else 0
            commission = _estimate_commission(market, trade_value)
            outcome = {
                "order_id": result.order_id,
                "symbol": result.symbol,
                "side": result.side,
                "quantity": result.quantity,
                "filled_price": effective_price,
                "status": result.status,
                "market": result.market,
                "commission": commission,
            }

            decisions_sink.append({
                "type": "trade",
                "action": side.upper(),
                "symbol": symbol,
                "quantity": quantity,
                "price": effective_price,
                "market": market,
                "exchange": exchange,
                "order_id": result.order_id,
                "status": result.status,
            })

            logger.info(
                "agent_order_submitted",
                agent=agent_name,
                symbol=symbol,
                side=side,
                quantity=quantity,
                status=result.status,
            )
            return _order(outcome)
        except Exception as e:
            logger.exception("agent_submit_order_failed", agent=agent_name, symbol=symbol)
            return f"ERR:{e}"

    async def cancel_order(
        order_id: str,
        market: str,
        symbol: str = "",
        quantity: float = 0.0,
    ) -> str:
        """Cancel a pending order."""
        if not trading:
            return "ERR:no_trading"
        try:
            success = await trading.cancel_order(order_id, symbol=symbol, quantity=quantity, market=market)
            return f"cancelled:{success},oid:{order_id}"
        except Exception as e:
            return f"ERR:{e}"

    # ---- Memory tools ----------------------------------------------------

    async def save_memory(content: str, keywords: list[str] | None = None) -> str:
        """Save a memory entry for future reference."""
        import time
        entry = {
            "content": content,
            "keywords": keywords or [],
            "timestamp": time.time(),
        }
        key = f"mem_{len(memory)}"
        memory[key] = entry
        return f"saved:1,key:{key}"

    async def search_memory(query: str, limit: int = 5) -> str:
        """Search agent memory by keyword or content match."""
        from agentic_capital.formats.compact import mem_entries
        query_lower = query.lower()
        results = []
        for entry in memory.values():
            content = entry.get("content", "").lower()
            kws = [k.lower() for k in entry.get("keywords", [])]
            if query_lower in content or any(query_lower in k for k in kws):
                results.append(entry)
            if len(results) >= limit:
                break
        return mem_entries(results)

    # ---- Messaging tools -------------------------------------------------

    async def send_message(to_agent: str, type: str = "SIG", content: str = "") -> str:
        """Send a compact message to another agent.

        content: compact k:v pairs e.g. "sym:005930,act:BUY,cf:0.87,why:RSI_OS"
        Full wire format: TYPE|FROM|TO|TS|content
        """
        from agentic_capital.formats.compact import msg_encode
        wire = msg_encode(type, agent_name, to_agent, content)
        msg = {
            "from": agent_name,
            "to": to_agent,
            "type": type,
            "content": content,
            "wire": wire,
        }
        messages_sink.append(msg)
        logger.info("agent_message_sent", from_agent=agent_name, to=to_agent, type=type)
        return "sent:1"

    # ---- Market data tools -----------------------------------------------

    async def get_quote(symbol: str) -> str:
        """Get current price quote. KR stocks: 6-digit code (005930). US: ticker (AAPL)."""
        if not market_data:
            return "ERR:no_market_data"
        try:
            from agentic_capital.formats.compact import quote as _quote
            q = await market_data.get_quote(symbol)
            return _quote(q.symbol, q.price, q.bid, q.ask, q.volume, q.currency)
        except Exception as e:
            return f"ERR:{e}"

    async def get_ohlcv(symbol: str, timeframe: str = "1d", limit: int = 20) -> str:
        """Get historical OHLCV candles. Returns TOON table. timeframe: 1m|5m|15m|60m|1d|1w|1mo|3mo"""
        if not market_data:
            return "ERR:no_market_data"
        try:
            from agentic_capital.formats.compact import ohlcv as _ohlcv
            candles = await market_data.get_ohlcv(symbol, timeframe=timeframe, limit=limit)
            return _ohlcv(symbol, candles)
        except Exception as e:
            return f"ERR:{e}"

    # ---- Timing control --------------------------------------------------

    async def request_wakeup(seconds: int) -> str:
        """Schedule next wakeup and END this cycle. Call this ONCE when done.

        After calling this, stop all tool calls and return your final response.
        Do NOT call this multiple times — only the first call is used.

        seconds=0: run again immediately
        seconds=60: wait 1 minute
        seconds=300: wait 5 minutes
        seconds=3600: wait 1 hour (max — HORIZON=1h)
        """
        capped = min(max(0, seconds), 3600)
        if not wakeup_sink:  # only first call counts
            wakeup_sink.append(capped)
        logger.info("agent_wakeup_requested", agent=agent_name, seconds=seconds)
        return f"CYCLE_DONE. Next wakeup in {capped}s. Stop here — do not call any more tools."

    # ---- Build tool list -----------------------------------------------

    tools = [
        StructuredTool.from_function(
            coroutine=get_balance,
            name="get_balance",
            description="Get current account balance (total equity, available cash, currency)",
        ),
        StructuredTool.from_function(
            coroutine=get_positions,
            name="get_positions",
            description="Get all open positions with quantity, avg price, unrealized P&L",
        ),
        StructuredTool.from_function(
            coroutine=get_fills,
            name="get_fills",
            description="Get order fill history for review",
            args_schema=GetFillsInput,
        ),
        StructuredTool.from_function(
            coroutine=submit_order,
            name="submit_order",
            description="Submit a buy or sell order. Any instrument: stocks, ETFs, leveraged ETFs, futures, options, derivatives. You decide market, symbol, and price. No restrictions.",
            args_schema=SubmitOrderInput,
        ),
        StructuredTool.from_function(
            coroutine=cancel_order,
            name="cancel_order",
            description="Cancel a pending order by order ID",
            args_schema=CancelOrderInput,
        ),
        StructuredTool.from_function(
            coroutine=save_memory,
            name="save_memory",
            description="Save analysis, observations, or decisions to memory for future cycles",
            args_schema=SaveMemoryInput,
        ),
        StructuredTool.from_function(
            coroutine=search_memory,
            name="search_memory",
            description="Search previous memories by keyword",
            args_schema=SearchMemoryInput,
        ),
        StructuredTool.from_function(
            coroutine=send_message,
            name="send_message",
            description="Send a message (signal, instruction, report) to another agent",
            args_schema=SendMessageInput,
        ),
        StructuredTool.from_function(
            coroutine=get_quote,
            name="get_quote",
            description="Get current price quote for any symbol. KR stocks/ETFs: 6-digit code (e.g. 005930, 069500). US stocks/ETFs: ticker (e.g. AAPL, SPY, TQQQ, SOXL).",
            args_schema=GetQuoteInput,
        ),
        StructuredTool.from_function(
            coroutine=get_ohlcv,
            name="get_ohlcv",
            description="Get historical OHLCV price candles for technical analysis. timeframe: 1d|60m|15m|5m|1w|1mo",
            args_schema=GetOHLCVInput,
        ),
        StructuredTool.from_function(
            coroutine=request_wakeup,
            name="request_wakeup",
            description="Control when this agent runs next. Agent decides its own cycle timing.",
            args_schema=RequestWakeupInput,
        ),
    ]

    return tools, decisions_sink, messages_sink, wakeup_sink


# ---------------------------------------------------------------------------
# Legacy class — kept for backward compatibility
# ---------------------------------------------------------------------------


class DataQueryTools:
    """Legacy data query class for backward compatibility.

    New code should use build_agent_tools() directly.
    """

    def __init__(self, *, trading: Any = None, market_data: Any = None, recorder: Any = None) -> None:
        self._trading = trading
        self._market_data = market_data
        self._recorder = recorder

    async def query_balance(self) -> dict:
        """Query current account balance."""
        if not self._trading:
            return {"error": "trading adapter not available"}
        try:
            bal = await self._trading.get_balance()
            return {"total": bal.total, "available": bal.available, "currency": bal.currency}
        except Exception as e:
            logger.warning("query_balance_failed", error=str(e))
            return {"error": str(e)}

    async def query_positions(self) -> list[dict]:
        """Query all open positions."""
        if not self._trading:
            return []
        try:
            positions = await self._trading.get_positions()
            return [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_price": p.avg_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl,
                    "unrealized_pnl_pct": p.unrealized_pnl_pct,
                }
                for p in positions
            ]
        except Exception as e:
            logger.warning("query_positions_failed", error=str(e))
            return []

    async def query_quote(self, symbol: str) -> dict:
        """Query current price quote for a symbol."""
        if not self._market_data:
            return {"error": "market data adapter not available"}
        try:
            quote = await self._market_data.get_quote(symbol)
            return {
                "symbol": symbol,
                "price": quote.price,
                "bid": quote.bid,
                "ask": quote.ask,
                "volume": quote.volume,
            }
        except Exception as e:
            logger.warning("query_quote_failed", symbol=symbol, error=str(e))
            return {"error": str(e)}

    async def query_quotes(self, symbols: list[str]) -> list[dict]:
        """Query quotes for multiple symbols."""
        results = []
        for symbol in symbols:
            result = await self.query_quote(symbol)
            if "error" not in result:
                results.append(result)
        return results

    async def query_ohlcv(self, symbol: str, timeframe: str = "1d", limit: int = 30) -> list[dict]:
        """Query historical OHLCV candles."""
        if not self._market_data:
            return []
        try:
            candles = await self._market_data.get_ohlcv(symbol, timeframe=timeframe, limit=limit)
            return [
                {
                    "timestamp": str(c.timestamp),
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                }
                for c in candles
            ]
        except Exception as e:
            logger.warning("query_ohlcv_failed", symbol=symbol, error=str(e))
            return []

    async def query_symbols(self) -> list[str]:
        """Query all available trading symbols."""
        if not self._market_data:
            return []
        try:
            return await self._market_data.get_symbols()
        except Exception as e:
            logger.warning("query_symbols_failed", error=str(e))
            return []

    def get_tool_descriptions(self) -> list[dict]:
        """Return tool descriptions for LLM function calling."""
        return [
            {"name": "query_balance", "description": "Get current account balance", "parameters": {}},
            {"name": "query_positions", "description": "Get all open positions with P&L", "parameters": {}},
            {"name": "query_quote", "description": "Get current price for a symbol", "parameters": {"symbol": "string"}},
            {"name": "query_quotes", "description": "Get current prices for multiple symbols", "parameters": {"symbols": "list[string]"}},
            {"name": "query_ohlcv", "description": "Get historical OHLCV candles", "parameters": {"symbol": "string", "timeframe": "string", "limit": "int"}},
            {"name": "query_symbols", "description": "Get all available trading symbols", "parameters": {}},
        ]

    async def execute_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Execute a tool by name."""
        tools_map = {
            "query_balance": self.query_balance,
            "query_positions": self.query_positions,
            "query_quote": self.query_quote,
            "query_quotes": self.query_quotes,
            "query_ohlcv": self.query_ohlcv,
            "query_symbols": self.query_symbols,
        }
        tool = tools_map.get(tool_name)
        if not tool:
            return {"error": f"Unknown tool: {tool_name}"}
        return await tool(**kwargs)
