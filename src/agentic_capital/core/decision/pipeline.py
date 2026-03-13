"""Decision pipeline — data collection → AI judgment → execution."""

from __future__ import annotations

import orjson
import structlog

from agentic_capital.core.decision.prompts import build_system_prompt, build_trading_prompt
from agentic_capital.core.personality.emotion import update_emotion_from_pnl
from agentic_capital.core.personality.models import EmotionState, PersonalityVector
from agentic_capital.ports.llm import LLMPort
from agentic_capital.ports.market_data import MarketDataPort
from agentic_capital.ports.trading import Order, OrderSide, OrderType, TradingPort

logger = structlog.get_logger()


class TradingDecision:
    """Single trading decision from LLM."""

    def __init__(self, action: str, symbol: str, quantity: int, reason: str, confidence: float = 0.5):
        self.action = action  # BUY, SELL, HOLD
        self.symbol = symbol
        self.quantity = quantity
        self.reason = reason
        self.confidence = confidence


class DecisionPipeline:
    """Orchestrates data → judgment → execution cycle for an agent."""

    def __init__(
        self,
        llm: LLMPort,
        trading: TradingPort,
        market_data: MarketDataPort,
    ) -> None:
        self._llm = llm
        self._trading = trading
        self._market_data = market_data

    async def run_cycle(
        self,
        agent_name: str,
        agent_role: str,
        philosophy: str,
        personality: PersonalityVector,
        emotion: EmotionState,
        symbols: list[str],
        recent_memories: list[str] | None = None,
    ) -> tuple[list[TradingDecision], EmotionState]:
        """Execute one full decision cycle.

        Returns:
            Tuple of (decisions executed, updated emotion state).
        """
        logger.info("pipeline_cycle_start", agent=agent_name, symbols_count=len(symbols))

        # 1. Collect market data
        market_data = await self._collect_market_data(symbols)

        # 2. Get account state
        balance = await self._trading.get_balance()
        positions = await self._trading.get_positions()

        pos_dicts = [
            {
                "symbol": p.symbol,
                "quantity": p.quantity,
                "avg_price": p.avg_price,
                "current_price": p.current_price,
                "unrealized_pnl_pct": p.unrealized_pnl_pct,
            }
            for p in positions
        ]

        # 3. Build prompts
        system = build_system_prompt(agent_name, agent_role, philosophy, personality, emotion)
        prompt = build_trading_prompt(
            balance=balance.available,
            positions=pos_dicts,
            market_data=market_data,
            recent_memories=recent_memories or [],
        )

        # 4. LLM judgment
        decisions = await self._get_llm_decisions(system, prompt, agent_name)

        # 5. Execute decisions
        executed = []
        total_pnl_pct = 0.0
        for decision in decisions:
            if decision.action == "HOLD":
                continue
            success = await self._execute_decision(decision, balance.available, agent_name)
            if success:
                executed.append(decision)

        # 6. Update emotion based on P&L
        if positions:
            total_pnl_pct = sum(p.unrealized_pnl_pct for p in positions) / len(positions)
        updated_emotion = update_emotion_from_pnl(emotion, total_pnl_pct / 100.0)

        logger.info(
            "pipeline_cycle_complete",
            agent=agent_name,
            decisions=len(decisions),
            executed=len(executed),
            pnl_pct=total_pnl_pct,
        )
        return executed, updated_emotion

    async def _collect_market_data(self, symbols: list[str]) -> list[dict]:
        """Collect current quotes for all symbols."""
        data = []
        for symbol in symbols:
            try:
                quote = await self._market_data.get_quote(symbol)
                data.append({
                    "symbol": symbol,
                    "price": quote.price,
                    "change_pct": 0.0,
                    "volume": quote.volume or 0,
                })
            except Exception:
                logger.warning("market_data_fetch_failed", symbol=symbol)
        return data

    async def _get_llm_decisions(
        self, system: str, prompt: str, agent_name: str
    ) -> list[TradingDecision]:
        """Get trading decisions from LLM."""
        try:
            response = await self._llm.generate(prompt, system=system)

            # Parse JSON from response (handle markdown code blocks)
            json_str = response.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            parsed = orjson.loads(json_str)
            decisions = []
            for d in parsed.get("decisions", []):
                action = d.get("action", "HOLD").upper()
                if action not in ("BUY", "SELL", "HOLD"):
                    continue
                decisions.append(TradingDecision(
                    action=action,
                    symbol=d.get("symbol", ""),
                    quantity=int(d.get("quantity", 0)),
                    reason=d.get("reason", ""),
                    confidence=float(parsed.get("confidence", 0.5)),
                ))

            logger.info("llm_decisions_parsed", agent=agent_name, count=len(decisions))
            return decisions
        except Exception:
            logger.exception("llm_decision_failed", agent=agent_name)
            return []

    async def _execute_decision(
        self, decision: TradingDecision, available_cash: float, agent_name: str
    ) -> bool:
        """Execute a single trading decision."""
        if decision.quantity <= 0 or not decision.symbol:
            return False

        try:
            side = OrderSide.BUY if decision.action == "BUY" else OrderSide.SELL

            # Get current price for limit order
            quote = await self._market_data.get_quote(decision.symbol)
            price = quote.price

            # Capital check for BUY
            if side == OrderSide.BUY:
                cost = price * decision.quantity
                if cost > available_cash:
                    max_qty = int(available_cash / price) if price > 0 else 0
                    if max_qty <= 0:
                        logger.warning(
                            "insufficient_capital",
                            agent=agent_name,
                            symbol=decision.symbol,
                            cost=cost,
                            available=available_cash,
                        )
                        return False
                    decision.quantity = max_qty

            order = Order(
                symbol=decision.symbol,
                side=side,
                order_type=OrderType.LIMIT,
                quantity=decision.quantity,
                price=price,
            )
            result = await self._trading.submit_order(order)

            logger.info(
                "order_executed",
                agent=agent_name,
                symbol=decision.symbol,
                side=decision.action,
                quantity=decision.quantity,
                price=price,
                status=result.status,
                reason=decision.reason,
            )
            return result.status in ("filled", "submitted")
        except Exception:
            logger.exception(
                "order_execution_failed",
                agent=agent_name,
                symbol=decision.symbol,
            )
            return False
