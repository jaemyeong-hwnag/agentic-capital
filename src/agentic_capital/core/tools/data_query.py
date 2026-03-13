"""Agent tools — all trading and data tools available to agents.

System provides these tools. Agents call them freely, in any order, any number
of times. No workflow. No restrictions beyond capital constraints.
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


class GetQuoteInput(BaseModel):
    symbol: str = Field(description="Ticker symbol, e.g. '005930' or 'AAPL'")
    market: str = Field(default="kr_stock", description="Market: kr_stock | us_stock | hk_stock | cn_stock | jp_stock | vn_stock")
    exchange: str | None = Field(default=None, description="Exchange code: NASD, NYSE, AMEX, SEHK, SHAA, SZAA, TKSE, HASE, VNSE")


class GetOHLCVInput(BaseModel):
    symbol: str = Field(description="Ticker symbol")
    timeframe: str = Field(default="1d", description="Candle period: 1d | 1w | 1mo | 1m | 3m | 5m | 10m | 15m | 30m | 60m")
    limit: int = Field(default=30, description="Number of candles to return")
    market: str = Field(default="kr_stock", description="Market")
    exchange: str | None = Field(default=None, description="Exchange code for overseas markets")


class GetOrderBookInput(BaseModel):
    symbol: str = Field(description="Domestic stock ticker symbol")
    depth: int = Field(default=10, description="Order book depth (max 10)")


class GetSymbolsInput(BaseModel):
    market: str = Field(default="kr_stock", description="Market to get symbols for")


class GetFillsInput(BaseModel):
    start_date: str | None = Field(default=None, description="Start date YYYYMMDD")
    end_date: str | None = Field(default=None, description="End date YYYYMMDD")
    symbol: str = Field(default="", description="Filter by symbol (empty = all)")


class SubmitOrderInput(BaseModel):
    symbol: str = Field(description="Ticker symbol to trade")
    side: str = Field(description="Trade direction: buy | sell")
    quantity: float = Field(description="Number of shares/units")
    price: float | None = Field(default=None, description="Limit price (omit for market order)")
    market: str = Field(default="kr_stock", description="Market")
    exchange: str | None = Field(default=None, description="Exchange code for overseas")


class CancelOrderInput(BaseModel):
    order_id: str = Field(description="Order ID to cancel")
    symbol: str = Field(default="", description="Symbol (required for some exchanges)")
    quantity: float = Field(default=0.0, description="Quantity (required for KIS cancel)")
    market: str = Field(default="kr_stock", description="Market")


class SaveMemoryInput(BaseModel):
    content: str = Field(description="Memory content to save")
    keywords: list[str] = Field(default_factory=list, description="Keywords for search")


class SearchMemoryInput(BaseModel):
    query: str = Field(description="Search query")
    limit: int = Field(default=5, description="Max results")


class SendMessageInput(BaseModel):
    to_agent: str = Field(description="Target agent name or ID")
    type: str = Field(default="SIGNAL", description="Message type: SIGNAL | INSTRUCTION | REPORT | QUERY | RESPONSE")
    content: dict = Field(description="Message content as dict")


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
) -> list:
    """Build LangChain StructuredTools bound to the given adapters.

    Returns a list of tools the agent can call freely during its cycle.
    """
    memory = agent_memory if agent_memory is not None else {}
    decisions_sink: list[dict] = []   # collects all decisions for recording
    messages_sink: list[dict] = []    # collects outbound messages

    # ---- Market data tools -----------------------------------------------

    async def get_balance() -> dict:
        """Get current account balance (total equity, available cash, currency)."""
        if not trading:
            return {"error": "trading adapter not available"}
        try:
            bal = await trading.get_balance()
            return {"total": bal.total, "available": bal.available, "currency": bal.currency}
        except Exception as e:
            return {"error": str(e)}

    async def get_positions() -> list[dict]:
        """Get all open positions with unrealized P&L."""
        if not trading:
            return []
        try:
            positions = await trading.get_positions()
            return [
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
            ]
        except Exception as e:
            return [{"error": str(e)}]

    async def get_quote(symbol: str, market: str = "kr_stock", exchange: str | None = None) -> dict:
        """Get current price quote for a symbol."""
        if not market_data:
            return {"error": "market data adapter not available"}
        try:
            quote = await market_data.get_quote(symbol, market=market, exchange=exchange)
            return {
                "symbol": quote.symbol,
                "price": quote.price,
                "bid": quote.bid,
                "ask": quote.ask,
                "volume": quote.volume,
                "market": quote.market,
                "currency": quote.currency,
            }
        except Exception as e:
            return {"error": str(e)}

    async def get_ohlcv(
        symbol: str,
        timeframe: str = "1d",
        limit: int = 30,
        market: str = "kr_stock",
        exchange: str | None = None,
    ) -> list[dict]:
        """Get historical OHLCV candles."""
        if not market_data:
            return []
        try:
            candles = await market_data.get_ohlcv(
                symbol, timeframe=timeframe, limit=limit, market=market, exchange=exchange
            )
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
            return [{"error": str(e)}]

    async def get_order_book(symbol: str, depth: int = 10) -> dict:
        """Get order book (호가창) for a domestic stock."""
        if not market_data:
            return {"error": "market data adapter not available"}
        try:
            book = await market_data.get_order_book(symbol, depth=depth)
            return {
                "symbol": book.symbol,
                "bids": [{"price": l.price, "quantity": l.quantity} for l in book.bids],
                "asks": [{"price": l.price, "quantity": l.quantity} for l in book.asks],
                "timestamp": str(book.timestamp),
            }
        except Exception as e:
            return {"error": str(e)}

    async def get_symbols(market: str = "kr_stock") -> list[str]:
        """Get available symbols for a market (starting set — any valid symbol works)."""
        if not market_data:
            return []
        try:
            return await market_data.get_symbols(market)
        except Exception as e:
            return []

    async def get_fills(
        start_date: str | None = None,
        end_date: str | None = None,
        symbol: str = "",
    ) -> list[dict]:
        """Get order fill history."""
        if not trading:
            return []
        try:
            fills = await trading.get_fills(start_date=start_date, end_date=end_date, symbol=symbol)
            return [
                {
                    "order_id": f.order_id,
                    "symbol": f.symbol,
                    "side": f.side,
                    "quantity": f.quantity,
                    "filled_price": f.filled_price,
                    "status": f.status,
                }
                for f in fills
            ]
        except Exception as e:
            return [{"error": str(e)}]

    # ---- Trading tools ---------------------------------------------------

    async def submit_order(
        symbol: str,
        side: str,
        quantity: float,
        price: float | None = None,
        market: str = "kr_stock",
        exchange: str | None = None,
    ) -> dict:
        """Submit a buy or sell order. Returns order result."""
        if not trading:
            return {"error": "trading adapter not available"}
        try:
            from agentic_capital.ports.trading import Market, Order, OrderSide, OrderType

            order = Order(
                symbol=symbol,
                side=OrderSide(side.lower()),
                order_type=OrderType.LIMIT if price is not None else OrderType.MARKET,
                quantity=quantity,
                price=price,
                market=Market(market),
                exchange=exchange,
            )
            result = await trading.submit_order(order)
            outcome = {
                "order_id": result.order_id,
                "symbol": result.symbol,
                "side": result.side,
                "quantity": result.quantity,
                "filled_price": result.filled_price,
                "status": result.status,
                "market": result.market,
            }

            # Record decision automatically
            decisions_sink.append({
                "type": "trade",
                "action": side.upper(),
                "symbol": symbol,
                "quantity": quantity,
                "price": price or result.filled_price,
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
            return outcome
        except Exception as e:
            logger.exception("agent_submit_order_failed", agent=agent_name, symbol=symbol)
            return {"error": str(e)}

    async def cancel_order(
        order_id: str,
        symbol: str = "",
        quantity: float = 0.0,
        market: str = "kr_stock",
    ) -> dict:
        """Cancel a pending order."""
        if not trading:
            return {"error": "trading adapter not available"}
        try:
            success = await trading.cancel_order(order_id, symbol=symbol, quantity=quantity, market=market)
            return {"cancelled": success, "order_id": order_id}
        except Exception as e:
            return {"error": str(e)}

    # ---- Memory tools ----------------------------------------------------

    async def save_memory(content: str, keywords: list[str] | None = None) -> dict:
        """Save a memory entry for future reference."""
        import time
        entry = {
            "content": content,
            "keywords": keywords or [],
            "timestamp": time.time(),
        }
        key = f"mem_{len(memory)}"
        memory[key] = entry
        return {"saved": True, "key": key}

    async def search_memory(query: str, limit: int = 5) -> list[dict]:
        """Search agent memory by keyword or content match."""
        query_lower = query.lower()
        results = []
        for entry in memory.values():
            content = entry.get("content", "").lower()
            kws = [k.lower() for k in entry.get("keywords", [])]
            if query_lower in content or any(query_lower in k for k in kws):
                results.append(entry)
            if len(results) >= limit:
                break
        return results

    # ---- Messaging tools -------------------------------------------------

    async def send_message(to_agent: str, type: str = "SIGNAL", content: dict | None = None) -> dict:
        """Send a message to another agent."""
        msg = {
            "from": agent_name,
            "to": to_agent,
            "type": type,
            "content": content or {},
        }
        messages_sink.append(msg)
        logger.info("agent_message_sent", from_agent=agent_name, to=to_agent, type=type)
        return {"sent": True}

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
            coroutine=get_quote,
            name="get_quote",
            description="Get current price quote for any symbol on any supported market",
            args_schema=GetQuoteInput,
        ),
        StructuredTool.from_function(
            coroutine=get_ohlcv,
            name="get_ohlcv",
            description="Get historical OHLCV candles. Supports daily, weekly, monthly, and minute timeframes",
            args_schema=GetOHLCVInput,
        ),
        StructuredTool.from_function(
            coroutine=get_order_book,
            name="get_order_book",
            description="Get real-time order book (bid/ask levels) for a domestic stock",
            args_schema=GetOrderBookInput,
        ),
        StructuredTool.from_function(
            coroutine=get_symbols,
            name="get_symbols",
            description="Get a list of tradable symbols for a market. Any valid exchange symbol works beyond this list.",
            args_schema=GetSymbolsInput,
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
            description="Submit a buy or sell order. Use market orders for immediate execution, limit for price control.",
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
    ]

    return tools, decisions_sink, messages_sink


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
