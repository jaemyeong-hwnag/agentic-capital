"""Simulation engine — main loop for autonomous trading."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

import structlog

from agentic_capital.adapters.kis_session import KISSession
from agentic_capital.adapters.llm.gemini import GeminiLLMAdapter
from agentic_capital.adapters.market_data.kis import KISMarketDataAdapter
from agentic_capital.adapters.trading.kis import KISTradingAdapter
from agentic_capital.config import settings
from agentic_capital.core.agents.factory import create_random_personality
from agentic_capital.core.decision.pipeline import DecisionPipeline
from agentic_capital.core.decision.reflection import reflect_on_trades
from agentic_capital.core.personality.models import EmotionState
from agentic_capital.simulation.clock import is_market_open, now_kst, seconds_until_market_open

logger = structlog.get_logger()


class AgentState:
    """Runtime state for a single trading agent."""

    def __init__(
        self,
        name: str,
        role: str = "trader",
        philosophy: str = "",
        seed: int | None = None,
    ) -> None:
        self.id = uuid.uuid4()
        self.name = name
        self.role = role
        self.philosophy = philosophy
        self.personality = create_random_personality(seed)
        self.emotion = EmotionState()
        self.memories: list[str] = []
        self.total_cycles = 0
        self.created_at = datetime.now()


class SimulationEngine:
    """Main simulation loop — creates agents, runs trading cycles."""

    def __init__(
        self,
        *,
        cycle_interval_seconds: int = 300,  # 5 minutes default
        symbols: list[str] | None = None,
    ) -> None:
        self._cycle_interval = cycle_interval_seconds
        self._symbols = symbols
        self._agents: list[AgentState] = []
        self._running = False
        self._cycle_count = 0

        # Adapters (initialized in start())
        self._llm: GeminiLLMAdapter | None = None
        self._trading: KISTradingAdapter | None = None
        self._market_data: KISMarketDataAdapter | None = None
        self._pipeline: DecisionPipeline | None = None
        self._recorder = None  # SimulationRecorder, optional (requires DB)

    def _init_adapters(self) -> None:
        """Initialize all adapters from settings."""
        self._llm = GeminiLLMAdapter()
        kis_session = KISSession()
        self._trading = KISTradingAdapter(session=kis_session)
        self._market_data = KISMarketDataAdapter(session=kis_session)
        self._pipeline = DecisionPipeline(
            llm=self._llm,
            trading=self._trading,
            market_data=self._market_data,
        )
        logger.info("adapters_initialized")

    def _init_agents(self) -> None:
        """Create initial agent roster."""
        seed = settings.simulation_seed
        self._agents = [
            AgentState(
                name="Alpha",
                role="aggressive_trader",
                philosophy="High risk, high reward. Momentum-based trading with conviction.",
                seed=seed,
            ),
            AgentState(
                name="Beta",
                role="conservative_trader",
                philosophy="Capital preservation first. Value investing with strong fundamentals.",
                seed=seed + 1,
            ),
            AgentState(
                name="Gamma",
                role="swing_trader",
                philosophy="Follow market trends. Technical analysis with risk management.",
                seed=seed + 2,
            ),
        ]
        logger.info("agents_initialized", count=len(self._agents))
        for agent in self._agents:
            logger.info(
                "agent_created",
                name=agent.name,
                role=agent.role,
                personality_snapshot={
                    "openness": f"{agent.personality.openness:.2f}",
                    "loss_aversion": f"{agent.personality.loss_aversion:.2f}",
                    "risk_aversion_gains": f"{agent.personality.risk_aversion_gains:.2f}",
                    "neuroticism": f"{agent.personality.neuroticism:.2f}",
                },
            )

    async def _init_recorder(self) -> None:
        """Initialize DB recorder if database is available."""
        try:
            from agentic_capital.infra.database import async_session
            from agentic_capital.simulation.recorder import SimulationRecorder

            session = async_session()
            self._recorder = SimulationRecorder(session)
            sim_id = await self._recorder.start_simulation(
                seed=settings.simulation_seed,
                initial_capital=settings.initial_capital,
                config={
                    "cycle_interval": self._cycle_interval,
                    "symbols": self._symbols or [],
                    "agents": [a.name for a in self._agents],
                },
            )

            # Record agents
            for agent in self._agents:
                await self._recorder.record_agent(
                    agent_id=agent.id,
                    name=agent.name,
                    role=agent.role,
                    philosophy=agent.philosophy,
                    personality=agent.personality,
                )

            await self._recorder.commit()
            logger.info("recorder_initialized", simulation_id=str(sim_id))
        except Exception:
            logger.warning("recorder_init_failed_running_without_db")
            self._recorder = None

    async def start(self) -> None:
        """Start the simulation loop."""
        logger.info(
            "simulation_starting",
            initial_capital=settings.initial_capital,
            seed=settings.simulation_seed,
            cycle_interval=self._cycle_interval,
        )

        self._init_adapters()
        self._init_agents()

        # Get symbols from market data adapter if not specified
        if not self._symbols:
            self._symbols = await self._market_data.get_symbols()

        # Initialize DB recorder
        await self._init_recorder()

        # Print initial state
        balance = await self._trading.get_balance()
        logger.info(
            "initial_state",
            balance_total=balance.total,
            balance_available=balance.available,
            currency=balance.currency,
            symbols=self._symbols[:5],
        )

        self._running = True
        try:
            while self._running:
                # Wait for market open
                wait_seconds = seconds_until_market_open()
                if wait_seconds > 0:
                    logger.info(
                        "waiting_for_market_open",
                        wait_seconds=wait_seconds,
                        current_time=now_kst().strftime("%H:%M:%S KST"),
                    )
                    # Sleep in chunks to allow clean shutdown
                    while wait_seconds > 0 and self._running:
                        chunk = min(wait_seconds, 60)
                        await asyncio.sleep(chunk)
                        wait_seconds -= chunk
                    if not self._running:
                        break

                await self._run_cycle()

                if self._running:
                    logger.info(
                        "cycle_sleeping",
                        next_cycle_in=f"{self._cycle_interval}s",
                        total_cycles=self._cycle_count,
                    )
                    await asyncio.sleep(self._cycle_interval)
        except asyncio.CancelledError:
            logger.info("simulation_cancelled")
        finally:
            self._running = False
            if self._recorder:
                await self._recorder.end_simulation("stopped")
                await self._recorder.commit()
            logger.info("simulation_stopped", total_cycles=self._cycle_count)

    def stop(self) -> None:
        """Signal the simulation to stop."""
        self._running = False

    async def _run_cycle(self) -> None:
        """Run one complete trading cycle for all agents."""
        if not is_market_open():
            logger.info("market_closed_skipping_cycle")
            return

        self._cycle_count += 1
        logger.info("cycle_start", cycle=self._cycle_count)

        balance = await self._trading.get_balance()
        logger.info(
            "cycle_balance",
            cycle=self._cycle_count,
            total=balance.total,
            available=balance.available,
        )

        for agent in self._agents:
            try:
                await self._run_agent_cycle(agent)
            except Exception:
                logger.exception("agent_cycle_failed", agent=agent.name, cycle=self._cycle_count)

        # Post-cycle summary
        balance_after = await self._trading.get_balance()
        positions = await self._trading.get_positions()
        logger.info(
            "cycle_complete",
            cycle=self._cycle_count,
            balance_before=balance.total,
            balance_after=balance_after.total,
            positions_count=len(positions),
        )

        # Record company snapshot
        if self._recorder:
            try:
                await self._recorder.record_company_snapshot(
                    total_capital=balance_after.total,
                    available_cash=balance_after.available,
                    agents_count=len(self._agents),
                )
                await self._recorder.commit()
            except Exception:
                logger.exception("snapshot_recording_failed")

    async def _run_agent_cycle(self, agent: AgentState) -> None:
        """Run one decision cycle for a single agent."""
        logger.info("agent_cycle_start", agent=agent.name, cycle=self._cycle_count)

        assert self._pipeline is not None

        # Run decision pipeline
        decisions, updated_emotion = await self._pipeline.run_cycle(
            agent_name=agent.name,
            agent_role=agent.role,
            philosophy=agent.philosophy,
            personality=agent.personality,
            emotion=agent.emotion,
            symbols=self._symbols or [],
            recent_memories=agent.memories[-5:],
        )

        # Update agent state
        agent.emotion = updated_emotion
        agent.total_cycles += 1

        # Reflect on outcomes
        positions = await self._trading.get_positions()
        total_pnl_pct = 0.0
        if positions:
            total_pnl_pct = sum(p.unrealized_pnl_pct for p in positions) / len(positions)

        old_personality = agent.personality
        updated_personality, drift_events = reflect_on_trades(
            agent.personality, decisions, total_pnl_pct
        )
        agent.personality = updated_personality

        # Store memory of this cycle
        if decisions:
            actions_summary = ", ".join(
                f"{d.action} {d.symbol} x{d.quantity}" for d in decisions
            )
            memory = f"Cycle {self._cycle_count}: {actions_summary}. P&L: {total_pnl_pct:.2f}%"
            agent.memories.append(memory)

        if drift_events:
            logger.info("personality_drift", agent=agent.name, drifts=len(drift_events))

        # Record to DB
        if self._recorder:
            try:
                for d in decisions:
                    await self._recorder.record_decision(
                        agent_id=agent.id,
                        decision=d,
                        personality=agent.personality,
                        emotion=agent.emotion,
                        status="executed",
                    )
                await self._recorder.record_emotion(
                    agent_id=agent.id,
                    emotion=agent.emotion,
                    trigger=f"cycle_{self._cycle_count}",
                )
                if drift_events:
                    drift_tuples = []
                    for event in drift_events:
                        param = event.get("parameter", "")
                        old_v = event.get("old_value", 0.0)
                        new_v = event.get("new_value", 0.0)
                        drift_tuples.append((param, old_v, new_v))
                    await self._recorder.record_personality_drift(
                        agent_id=agent.id,
                        drift_events=drift_tuples,
                        trigger=f"pnl_{total_pnl_pct:.2f}%",
                    )
                await self._recorder.commit()
            except Exception:
                logger.exception("recording_failed", agent=agent.name)

        logger.info(
            "agent_cycle_complete",
            agent=agent.name,
            decisions=len(decisions),
            emotion_valence=f"{agent.emotion.valence:.2f}",
            emotion_stress=f"{agent.emotion.stress:.2f}",
        )
