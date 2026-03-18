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
from agentic_capital.core.agents.factory import create_agent, create_random_personality
from agentic_capital.core.personality.models import EmotionState
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

    def _init_adapters(self) -> None:
        setup_tracing()
        from agentic_capital.adapters.kis_session import KISSession
        from agentic_capital.adapters.trading.kis import KISTradingAdapter
        from agentic_capital.adapters.trading.futures_guard import FuturesSessionGuard

        kis_session = KISSession()
        raw_trading = KISTradingAdapter(session=kis_session)
        self._trading = FuturesSessionGuard(raw_trading)

    def _init_recorder(self, simulation_id: uuid.UUID) -> None:
        from agentic_capital.infra.database import async_session
        from agentic_capital.simulation.recorder import SimulationRecorder
        self._recorder = SimulationRecorder(
            session=async_session(),
            simulation_id=simulation_id,
        )

    def _create_agent(self, simulation_id: uuid.UUID) -> None:
        """Create single futures scalping trader agent."""
        personality = create_random_personality()
        emotion = EmotionState()
        self._agent = create_agent(
            role="trader",
            name="Scalper-Alpha",
            simulation_id=simulation_id,
            personality=personality,
            emotion=emotion,
            initial_capital=self._capital_limit,
            philosophy="Scalp KR futures for consistent intraday profit. "
                        "Choose symbols autonomously. Enter on momentum/reversal signals. Exit quickly. "
                        "Close ALL before switching symbols. No overnight positions.",
        )

    async def _run_cycle(self) -> float:
        """Run one agent cycle. Returns next wakeup seconds."""
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

        # Sync guard state from live positions on each cycle
        if hasattr(self._trading, "sync_state"):
            await self._trading.sync_state()

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

        simulation_id = uuid.uuid4()
        self._init_recorder(simulation_id)
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
