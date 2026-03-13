"""Simulation engine — main loop for autonomous trading."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

import structlog

from agentic_capital.adapters.llm.gemini import GeminiLLMAdapter
from agentic_capital.adapters.market_data.kis import KISMarketDataAdapter
from agentic_capital.adapters.trading.kis import KISTradingAdapter
from agentic_capital.config import settings
from agentic_capital.core.agents.factory import create_random_personality
from agentic_capital.core.decision.pipeline import DecisionPipeline
from agentic_capital.core.decision.reflection import reflect_on_trades
from agentic_capital.core.personality.models import EmotionState

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

    def _init_adapters(self) -> None:
        """Initialize all adapters from settings."""
        self._llm = GeminiLLMAdapter()
        self._trading = KISTradingAdapter()
        self._market_data = KISMarketDataAdapter()
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
            logger.info("simulation_stopped", total_cycles=self._cycle_count)

    def stop(self) -> None:
        """Signal the simulation to stop."""
        self._running = False

    async def _run_cycle(self) -> None:
        """Run one complete trading cycle for all agents."""
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

        logger.info(
            "agent_cycle_complete",
            agent=agent.name,
            decisions=len(decisions),
            emotion_valence=f"{agent.emotion.valence:.2f}",
            emotion_stress=f"{agent.emotion.stress:.2f}",
        )
