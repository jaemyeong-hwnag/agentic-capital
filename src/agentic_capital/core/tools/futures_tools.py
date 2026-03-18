"""Futures-specific AI tools — single-symbol scalping.

Tools exposed to the futures trader agent:
- get_futures_balance()       current margin account state
- get_futures_positions()     active contracts
- get_futures_quote(symbol)   real-time price + OHLC
- get_active_symbol()         which symbol is locked (if any)
- submit_futures_order(...)   enter/exit with explicit position_effect
- close_all_positions()       close everything (required before symbol switch)
- request_wakeup(seconds)     control next cycle timing
"""

from __future__ import annotations

from typing import Any

import structlog
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agentic_capital.ports.trading import Market, Order, OrderSide, OrderType

logger = structlog.get_logger()

# KOSPI 200 futures: multiplier 250,000 KRW per point, tick 0.05pt = 12,500 KRW
_KOSPI200_MULTIPLIER = 250_000
_KOSPI200_TICK = 0.05


class SubmitFuturesOrderInput(BaseModel):
    symbol: str = Field(description="Futures symbol (AI chooses autonomously)")
    side: str = Field(description="'buy' or 'sell'")
    quantity: int = Field(description="Number of contracts (최소 1계약)")
    position_effect: str = Field(description="'open' = 신규진입 | 'close' = 청산. Must be explicit.")
    price: float | None = Field(default=None, description="Limit price (None = market order)")
    reason: str = Field(default="", description="Trade rationale for record")


class RequestWakeupInput(BaseModel):
    seconds: int = Field(description="Seconds until next cycle")


def build_futures_tools(
    *,
    trading: Any = None,
    recorder: Any = None,
    agent_id: str = "",
    agent_name: str = "",
    capital_limit: float | None = None,
) -> tuple[list, list, list]:
    """Build futures-specific tool list for the scalping agent.

    Returns: (tools, decisions_sink, wakeup_sink)
    """
    decisions_sink: list[dict] = []
    wakeup_sink: list[int] = []

    # ── Balance ───────────────────────────────────────────────────────────────

    async def get_futures_balance() -> str:
        """Get margin account balance.

        Returns: tot(total equity), avl(available margin), margin_used,
                 pnl_today, fee_today, op_cost(10000/day), net_today.
        """
        if not trading:
            return "ERR:no_trading"
        try:
            b = await trading.get_balance()
            total = min(b.total, capital_limit) if capital_limit else b.total
            available = min(b.available, capital_limit) if capital_limit else b.available

            # Overseas KRW P&L
            ovs_pnl = 0.0
            if hasattr(trading, "get_overseas_balance"):
                try:
                    ob = await trading.get_overseas_balance("USD")
                    ovs_pnl = ob.daily_pnl
                except Exception:
                    pass

            total_pnl = b.daily_pnl + ovs_pnl
            net = total_pnl - 10_000  # op_cost
            return (
                f"tot:{total:.0f},avl:{available:.0f},ccy:{b.currency}"
                f",pnl_today:{total_pnl:.0f},fee_today:{b.daily_fee:.0f}"
                f",op_cost:10000,net_today:{net:.0f}"
            )
        except Exception as e:
            return f"ERR:{e}"

    # ── Positions ─────────────────────────────────────────────────────────────

    async def get_futures_positions() -> str:
        """Get open futures positions with margin and P&L per contract.

        Returns TOON table: sym,side,qty,avg,cur,pnl,margin,mult,exp
        KOSPI200 multiplier = 250,000 KRW/pt. pnl = (cur-avg)*mult*qty
        """
        if not trading:
            return "@fut[0](sym,side,qty,avg,cur,pnl,margin,mult,exp)"
        try:
            positions = await trading.get_positions()
            fut = [p for p in positions if p.market in (Market.KR_FUTURES, Market.KR_OPTIONS)]
            if not fut:
                return "@fut[0](sym,side,qty,avg,cur,pnl,margin,mult,exp)"
            from agentic_capital.formats.toon import to_toon
            from agentic_capital.ports.trading import FuturesPosition
            rows = []
            for p in fut:
                mult = p.multiplier if isinstance(p, FuturesPosition) else _KOSPI200_MULTIPLIER
                margin = p.margin_required if isinstance(p, FuturesPosition) else 0.0
                exp = p.expiry if isinstance(p, FuturesPosition) else ""
                net_side = p.net_side if isinstance(p, FuturesPosition) else "long"
                rows.append([
                    p.symbol, net_side, str(int(p.quantity)),
                    f"{p.avg_price:.2f}", f"{p.current_price:.2f}",
                    f"{p.unrealized_pnl:.0f}", f"{margin:.0f}",
                    str(int(mult)), exp or "",
                ])
            return to_toon("fut", ["sym", "side", "qty", "avg", "cur", "pnl", "margin", "mult", "exp"], rows)
        except Exception as e:
            return f"ERR:{e}"

    # ── Quote ─────────────────────────────────────────────────────────────────

    async def get_futures_quote(symbol: str) -> str:
        """Get real-time futures price.

        Returns: sym,px,open,high,low,vol,chg,chg_pct
        """
        if not trading:
            return "ERR:no_trading"
        try:
            if hasattr(trading, "get_futures_quote"):
                q = await trading.get_futures_quote(symbol)
            elif hasattr(trading, "_inner") and hasattr(trading._inner, "get_futures_quote"):
                q = await trading._inner.get_futures_quote(symbol)
            else:
                return "ERR:futures_quote_not_supported"
            if not q:
                return f"ERR:no_data:{symbol}"
            return (
                f"sym:{q['symbol']},px:{q['price']:.2f},"
                f"o:{q['open']:.2f},h:{q['high']:.2f},l:{q['low']:.2f},"
                f"vol:{q['volume']},chg:{q['change']:.2f},pct:{q['change_pct']:.2f}"
            )
        except Exception as e:
            return f"ERR:{e}"

    # ── Active symbol lock ────────────────────────────────────────────────────

    async def get_active_symbol() -> str:
        """Check which futures symbol is currently locked (if any).

        Returns current locked symbol or 'none'.
        You must close_all_positions() before switching to a different symbol.
        """
        if hasattr(trading, "active_symbol"):
            sym = trading.active_symbol
            return f"locked:{sym}" if sym else "none"
        return "none"

    # ── Order submission ──────────────────────────────────────────────────────

    async def submit_futures_order(
        symbol: str,
        side: str,
        quantity: int,
        position_effect: str,
        price: float | None = None,
        reason: str = "",
    ) -> str:
        """Submit a futures order.

        position_effect MUST be explicit:
          open  = 신규진입 (opening a new position)
          close = 청산 (closing existing position)

        Single-symbol rule: if a different symbol is locked, this will be rejected.
        Use close_all_positions() first, then open new symbol.
        """
        if not trading:
            return "ERR:no_trading"
        try:
            order = Order(
                symbol=symbol,
                side=OrderSide(side.lower()),
                order_type=OrderType.LIMIT if price else OrderType.MARKET,
                quantity=float(quantity),
                price=price,
                market=Market.KR_FUTURES,
                position_effect=position_effect,
            )
            result = await trading.submit_order(order)

            if result.status == "rejected":
                err = result.metadata.get("error", "rejected")
                return f"ERR:{err}"

            decision = {
                "type": "trade",
                "action": side.upper(),
                "symbol": symbol,
                "quantity": quantity,
                "price": price or result.filled_price,
                "market": "kr_futures",
                "position_effect": position_effect,
                "reason": reason,
                "confidence": 0.7,
                "order_id": result.order_id,
                "status": result.status,
                "commission": 0.0,
            }
            decisions_sink.append(decision)

            logger.info(
                "futures_order_submitted",
                agent=agent_name,
                symbol=symbol,
                side=side,
                qty=quantity,
                effect=position_effect,
                status=result.status,
            )
            return (
                f"oid:{result.order_id},sym:{symbol},sd:{side[:1].upper()},"
                f"qty:{quantity},pe:{position_effect},st:{result.status}"
            )
        except Exception as e:
            return f"ERR:{e}"

    # ── Close all ─────────────────────────────────────────────────────────────

    async def close_all_positions() -> str:
        """Close ALL open futures positions immediately (market order).

        REQUIRED before switching to a different symbol.
        No rollovers — this closes contracts outright.
        """
        if not trading:
            return "ERR:no_trading"
        try:
            positions = await trading.get_positions()
            fut = [p for p in positions if p.market in (Market.KR_FUTURES, Market.KR_OPTIONS)]
            if not fut:
                return "OK:no_positions_to_close"

            results = []
            for p in fut:
                from agentic_capital.ports.trading import FuturesPosition
                # Close opposite side
                close_side = "sell" if (not isinstance(p, FuturesPosition) or p.net_side == "long") else "buy"
                order = Order(
                    symbol=p.symbol,
                    side=OrderSide(close_side),
                    order_type=OrderType.MARKET,
                    quantity=p.quantity,
                    market=Market.KR_FUTURES,
                    position_effect="close",
                )
                result = await trading.submit_order(order)
                results.append(f"{p.symbol}:{result.status}")
                decisions_sink.append({
                    "type": "trade", "action": close_side.upper(),
                    "symbol": p.symbol, "quantity": p.quantity,
                    "market": "kr_futures", "position_effect": "close",
                    "reason": "close_all_before_switch", "confidence": 1.0,
                    "order_id": result.order_id, "status": result.status,
                })

            logger.info("futures_close_all", agent=agent_name, results=results)
            return f"OK:closed|{','.join(results)}"
        except Exception as e:
            return f"ERR:{e}"

    # ── Timing ────────────────────────────────────────────────────────────────

    async def request_wakeup(seconds: int) -> str:
        """Schedule next wakeup and END this cycle.

        seconds=60: active scalping
        seconds=300: watching
        seconds=1800: low activity
        seconds=3600: between sessions
        seconds=7200: waiting for next session (max)

        COST: each cycle costs money. Sleep longer when market closed.
        """
        capped = min(max(0, seconds), 7200)
        if not wakeup_sink:
            wakeup_sink.append(capped)
        logger.info("futures_wakeup_requested", agent=agent_name, seconds=capped)
        return f"CYCLE_DONE. Next wakeup in {capped}s. Stop — do not call more tools."

    # ── Register tools ────────────────────────────────────────────────────────

    tools = [
        StructuredTool.from_function(
            coroutine=get_futures_balance,
            name="get_futures_balance",
            description="Get margin account balance with daily P&L and op cost.",
        ),
        StructuredTool.from_function(
            coroutine=get_futures_positions,
            name="get_futures_positions",
            description="Get open futures positions (sym, side, qty, avg, cur, pnl, margin).",
        ),
        StructuredTool.from_function(
            coroutine=get_futures_quote,
            name="get_futures_quote",
            description="Real-time futures price for any KR futures symbol.",
            args_schema=type("FuturesQuoteInput", (BaseModel,), {
                "symbol": Field(str, description="Futures symbol"),
                "__annotations__": {"symbol": str},
            }),
        ),
        StructuredTool.from_function(
            coroutine=get_active_symbol,
            name="get_active_symbol",
            description="Check which symbol is currently locked. Must close_all before switching.",
        ),
        StructuredTool.from_function(
            coroutine=submit_futures_order,
            name="submit_futures_order",
            description=(
                "Submit futures order. position_effect='open'(신규) or 'close'(청산) — REQUIRED. "
                "Single-symbol lock: different symbol rejected until close_all_positions()."
            ),
            args_schema=SubmitFuturesOrderInput,
        ),
        StructuredTool.from_function(
            coroutine=close_all_positions,
            name="close_all_positions",
            description="Close ALL open futures positions (market order). Required before switching symbol.",
        ),
        StructuredTool.from_function(
            coroutine=request_wakeup,
            name="request_wakeup",
            description="End cycle and schedule next wakeup.",
            args_schema=RequestWakeupInput,
        ),
    ]

    return tools, decisions_sink, wakeup_sink
