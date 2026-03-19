"""Futures scalping engine — single-symbol, single-agent loop.

Rules (system-enforced):
- ONE futures symbol active at a time (FuturesSessionGuard)
- Close ALL positions before switching symbols (guard blocks cross-symbol orders)
- No rollover — close outright, then re-enter new contract
"""

from __future__ import annotations

import asyncio
import uuid

import structlog

from agentic_capital.config import settings
from agentic_capital.core.agents.factory import create_agent_profile, create_random_personality
from agentic_capital.graph.workflow import run_agent_cycle
from agentic_capital.infra.tracing import setup_tracing
from agentic_capital.simulation.clock import get_open_markets, is_market_open

logger = structlog.get_logger()

_DEFAULT_CYCLE_SECONDS = 60


class FuturesEngine:
    """Single-agent futures scalping loop.

    Uses FuturesSessionGuard to enforce single-symbol rule.
    Agent uses futures_tools exclusively (no stock tools).
    """

    def __init__(self) -> None:
        self._trading = None
        self._recorder = None
        self._agent = None
        self._running = False
        self._cycle_count = 0
        self._capital_limit: float = float(settings.initial_capital)
        self._max_contracts: int = settings.futures_max_contracts
        self._max_daily_loss: float = self._capital_limit * settings.futures_daily_loss_pct

    def _init_adapters(self) -> None:
        setup_tracing()
        from agentic_capital.adapters.kis_session import KISSession
        from agentic_capital.adapters.trading.kis import KISTradingAdapter
        from agentic_capital.adapters.trading.futures_guard import FuturesSessionGuard
        from agentic_capital.adapters.trading.futures_virtual import FuturesVirtualAdapter
        from agentic_capital.config import settings

        kis_session = KISSession()
        raw_trading = KISTradingAdapter(session=kis_session)

        # KIS paper trading requires separate 선물옵션 모의투자 registration.
        # If not available (is_paper=True), wrap with virtual adapter that
        # simulates futures orders locally using Yahoo Finance prices.
        if settings.kis_is_paper:
            wrapped = FuturesVirtualAdapter(raw_trading, initial_capital=self._capital_limit)
        else:
            wrapped = raw_trading

        self._trading = FuturesSessionGuard(
            wrapped,
            capital_limit=self._capital_limit,
            max_contracts=self._max_contracts,
            max_daily_loss=self._max_daily_loss,
        )

    async def _init_recorder(self) -> uuid.UUID:
        """Initialize recorder and return simulation_id. Falls back to random UUID on error."""
        try:
            from agentic_capital.infra.database import async_session
            from agentic_capital.simulation.recorder import SimulationRecorder
            from agentic_capital.config import settings
            self._recorder = SimulationRecorder(session=async_session())
            sim_id = await self._recorder.start_simulation(
                seed=settings.simulation_seed,
                initial_capital=self._capital_limit,
                config={"mode": "futures_scalping"},
            )
            await self._recorder.commit()
            return sim_id
        except Exception:
            logger.warning("futures_recorder_init_failed_running_without_db")
            self._recorder = None
            return uuid.uuid4()

    def _create_agent(self, simulation_id: uuid.UUID) -> None:
        """Create single futures scalping trader agent.

        FuturesEngine uses the agent purely as a state container (profile,
        personality, emotion, agent_id). Actual LLM reasoning happens via the
        LangGraph ReAct loop in _run_cycle — no LLMPort needed here.
        """
        from agentic_capital.core.agents.base import BaseAgent
        from agentic_capital.core.personality.models import EmotionState

        personality = create_random_personality()
        profile = create_agent_profile(
            name="Scalper-Alpha",
            philosophy=(
                "Scalp KR futures for consistent intraday profit. "
                "Choose symbols autonomously. Enter on momentum/reversal signals. Exit quickly. "
                "Close ALL before switching symbols. No overnight positions."
            ),
            allocated_capital=self._capital_limit,
        )

        class _ScalperAgent(BaseAgent):
            async def think(self, context):
                return {}

            async def reflect(self, outcome):
                pass

        self._agent = _ScalperAgent(profile=profile, personality=personality)

    def _minutes_until_session_end(self) -> float:
        """Minutes until the current KR futures session closes. Returns 9999 if mid-session far from end."""
        from datetime import datetime, timezone, timedelta, time as dtime
        KST = timezone(timedelta(hours=9))
        now = datetime.now(KST)
        t = now.time()

        # KRX day session: 09:00–15:45 KST
        if dtime(9, 0) <= t < dtime(15, 45):
            end = now.replace(hour=15, minute=45, second=0, microsecond=0)
            return (end - now).total_seconds() / 60

        # KRX night session: 18:00–05:00 KST (spans midnight)
        if t >= dtime(18, 0):
            end = (now + timedelta(days=1)).replace(hour=5, minute=0, second=0, microsecond=0)
            return (end - now).total_seconds() / 60
        if t < dtime(5, 0):
            end = now.replace(hour=5, minute=0, second=0, microsecond=0)
            return (end - now).total_seconds() / 60

        return 9999.0  # between sessions

    async def _close_all_now(self, reason: str = "") -> None:
        """Force-close all open futures positions (market order)."""
        from agentic_capital.ports.trading import FuturesPosition, Market, Order, OrderSide, OrderType
        try:
            positions = await self._trading.get_positions()
            for p in positions:
                if p.market not in (Market.KR_FUTURES, Market.KR_OPTIONS):
                    continue
                close_side = (
                    OrderSide.SELL
                    if (not isinstance(p, FuturesPosition) or p.net_side == "long")
                    else OrderSide.BUY
                )
                order = Order(
                    symbol=p.symbol,
                    side=close_side,
                    order_type=OrderType.MARKET,
                    quantity=p.quantity,
                    market=p.market,
                    position_effect="close",
                    multiplier=p.multiplier if isinstance(p, FuturesPosition) else None,
                )
                await self._trading.submit_order(order)
                logger.info("futures_engine_pre_close", symbol=p.symbol, reason=reason)
        except Exception:
            logger.warning("futures_engine_pre_close_failed", reason=reason)

    async def _run_cycle(self) -> float:
        """Run one agent cycle. Returns next wakeup seconds.

        If no futures market is open, skip AI call entirely and sleep until
        the next session — avoids wasting LLM tokens when nothing can trade.
        """
        self._cycle_count += 1
        open_markets = get_open_markets()
        futures_open = "KRX" in open_markets or "NIGHT" in open_markets

        logger.info(
            "futures_cycle_start",
            cycle=self._cycle_count,
            futures_open=futures_open,
            open_markets=open_markets,
            active_symbol=getattr(self._trading, "active_symbol", None),
        )

        if not futures_open:
            from agentic_capital.simulation.clock import _is_night_session_open, _NIGHT_SESSIONS
            from datetime import datetime, timezone, timedelta
            # Compute seconds until KRX NIGHT session (18:00 KST)
            KST = timezone(timedelta(hours=9))
            now = datetime.now(KST)
            night_open = now.replace(hour=18, minute=0, second=0, microsecond=0)
            if now.time().hour >= 18:
                night_open += timedelta(days=1)
            wait = int((night_open - now).total_seconds())
            # Cap at 1h so we recheck frequently near session open
            sleep_secs = min(max(wait, 60), 3600)
            logger.info(
                "futures_market_closed_sleeping",
                night_session_in=f"{wait}s",
                sleeping=f"{sleep_secs}s",
            )
            return float(sleep_secs)

        # Session-end auto-close: liquidate all positions 10 min before close
        mins_left = self._minutes_until_session_end()
        if mins_left <= 10 and getattr(self._trading, "active_symbol", None):
            logger.warning(
                "futures_pre_close_session_end",
                minutes_left=round(mins_left, 1),
            )
            await self._close_all_now(reason="session_end")
            # Sleep past session end + 5 min buffer
            return float(max(int(mins_left * 60) + 300, 300))

        # Sync guard state from live positions on each cycle
        if hasattr(self._trading, "sync_state"):
            await self._trading.sync_state()

        # Capital safety: force-close if unrealized loss >= capital_limit
        if hasattr(self._trading, "enforce_capital_limit"):
            closed = await self._trading.enforce_capital_limit()
            if closed:
                logger.warning(
                    "futures_capital_limit_enforced",
                    cycle=self._cycle_count,
                    capital_limit=self._capital_limit,
                )

        from agentic_capital.core.tools.futures_tools import build_futures_tools
        tools, decisions_sink, wakeup_sink = build_futures_tools(
            trading=self._trading,
            recorder=self._recorder,
            agent_id=str(self._agent.agent_id),
            agent_name=self._agent.name,
            capital_limit=self._capital_limit,
        )

        # Build futures-specific system prompt
        from agentic_capital.formats.compact import LEGEND, MANDATE_FUTURES
        from agentic_capital.formats.compact import psych
        system_prompt = (
            f"{LEGEND}\n"
            f"<agent name=\"{self._agent.name}\" role=\"futures_scalper\">\n"
            f"<phi>{self._agent.profile.philosophy}</phi>\n"
            f"{psych(self._agent.personality, self._agent.emotion)}\n"
            f"</agent>\n"
            f"{MANDATE_FUTURES}"
        )

        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage
        from langgraph.prebuilt import create_react_agent

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.gemini_api_key,
            temperature=0.7,
        )
        react_agent = create_react_agent(llm, tools, prompt=system_prompt)

        from datetime import datetime
        started_at = datetime.now()

        try:
            result = await react_agent.ainvoke(
                {"messages": [HumanMessage(content=f"cycle:{self._cycle_count}")]},
                config={"recursion_limit": 100},
            )
            result_messages = result.get("messages", [])
        except Exception:
            logger.exception("futures_cycle_failed", cycle=self._cycle_count)
            result_messages = []

        completed_at = datetime.now()

        # Record cycle to DB
        if self._recorder:
            from agentic_capital.graph.workflow import _extract_tool_sequence, _extract_llm_reasoning
            from agentic_capital.graph.nodes import record_cycle
            await record_cycle(
                agent=self._agent,
                cycle_number=self._cycle_count,
                decisions=decisions_sink,
                messages=[],
                recorder=self._recorder,
            )
            tool_seq = _extract_tool_sequence(result_messages)
            reasoning = _extract_llm_reasoning(result_messages)
            emotion_snap = {
                "V": round(self._agent.emotion.valence, 2),
                "AR": round(self._agent.emotion.arousal, 2),
                "D": round(self._agent.emotion.dominance, 2),
                "ST": round(self._agent.emotion.stress, 2),
                "CF": round(self._agent.emotion.confidence, 2),
            }
            try:
                await self._recorder.record_agent_cycle(
                    agent_id=self._agent.agent_id,
                    agent_name=self._agent.name,
                    cycle_number=self._cycle_count,
                    tool_sequence=tool_seq,
                    llm_reasoning=reasoning,
                    emotion_snapshot=emotion_snap,
                    started_at=started_at,
                    completed_at=completed_at,
                    decisions_count=len(decisions_sink),
                    errors_count=0,
                    next_cycle_seconds=wakeup_sink[-1] if wakeup_sink else 0,
                )
                await self._recorder.commit()
            except Exception:
                logger.warning("futures_cycle_record_failed")

        next_secs = wakeup_sink[-1] if wakeup_sink else _DEFAULT_CYCLE_SECONDS
        logger.info(
            "futures_cycle_complete",
            cycle=self._cycle_count,
            decisions=len(decisions_sink),
            next_secs=next_secs,
        )
        return float(next_secs)

    async def start(self) -> None:
        """Start the futures scalping loop."""
        self._running = True
        self._init_adapters()

        simulation_id = await self._init_recorder()
        self._create_agent(simulation_id)

        # Sync guard from live positions
        if hasattr(self._trading, "sync_state"):
            await self._trading.sync_state()

        logger.info(
            "futures_engine_started",
            simulation_id=str(simulation_id),
            agent=self._agent.name,
            capital_limit=self._capital_limit,
            active_symbol=getattr(self._trading, "active_symbol", None),
        )

        while self._running:
            try:
                next_delay = await self._run_cycle()
                logger.info("futures_sleeping", next_cycle_in=f"{next_delay}s")
                await asyncio.sleep(next_delay)
            except KeyboardInterrupt:
                logger.info("futures_engine_stopped_by_user")
                self._running = False
            except Exception:
                logger.exception("futures_engine_cycle_error")
                await asyncio.sleep(30)
