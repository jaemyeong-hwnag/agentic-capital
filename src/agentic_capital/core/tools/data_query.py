"""Data query tools — agents autonomously decide what to query.

System provides these tools. Agents decide when and how to use them.
No restrictions on what data an agent can access.
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


class DataQueryTools:
    """Collection of data query functions available to all agents.

    Agents autonomously decide which queries to run.
    System provides access — agents decide what to look at.
    """

    def __init__(
        self,
        *,
        trading: Any = None,
        market_data: Any = None,
        recorder: Any = None,
    ) -> None:
        self._trading = trading
        self._market_data = market_data
        self._recorder = recorder

    async def query_balance(self) -> dict:
        """Query current account balance."""
        if not self._trading:
            return {"error": "trading adapter not available"}
        try:
            balance = await self._trading.get_balance()
            return {
                "total": balance.total,
                "available": balance.available,
                "currency": balance.currency,
            }
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

    async def query_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        limit: int = 30,
    ) -> list[dict]:
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
        """Return tool descriptions for LLM function calling.

        These descriptions are provided to agents so they can
        autonomously decide which tools to use.
        """
        return [
            {
                "name": "query_balance",
                "description": "Get current account balance (total, available, currency)",
                "parameters": {},
            },
            {
                "name": "query_positions",
                "description": "Get all open positions with P&L",
                "parameters": {},
            },
            {
                "name": "query_quote",
                "description": "Get current price for a symbol",
                "parameters": {"symbol": "string — ticker symbol"},
            },
            {
                "name": "query_quotes",
                "description": "Get current prices for multiple symbols",
                "parameters": {"symbols": "list[string] — ticker symbols"},
            },
            {
                "name": "query_ohlcv",
                "description": "Get historical price candles (OHLCV)",
                "parameters": {
                    "symbol": "string — ticker symbol",
                    "timeframe": "string — candle period (1m/5m/1h/1d), default 1d",
                    "limit": "int — number of candles, default 30",
                },
            },
            {
                "name": "query_symbols",
                "description": "Get all available trading symbols",
                "parameters": {},
            },
        ]

    async def execute_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Execute a tool by name — agents call this autonomously."""
        tools = {
            "query_balance": self.query_balance,
            "query_positions": self.query_positions,
            "query_quote": self.query_quote,
            "query_quotes": self.query_quotes,
            "query_ohlcv": self.query_ohlcv,
            "query_symbols": self.query_symbols,
        }

        tool = tools.get(tool_name)
        if not tool:
            return {"error": f"Unknown tool: {tool_name}"}

        return await tool(**kwargs)
