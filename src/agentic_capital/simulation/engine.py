"""Simulation engine — LangGraph-based autonomous multi-agent loop.

System provides the structure and records everything.
Agents decide everything autonomously. Only constraint: capital.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

import structlog

from agentic_capital.config import settings
from agentic_capital.core.agents.base import BaseAgent
from agentic_capital.core.agents.factory import create_agent, create_random_personality
from agentic_capital.core.personality.models import EmotionState
from agentic_capital.graph.workflow import run_agent_cycle
from agentic_capital.infra.tracing import setup_tracing
from agentic_capital.simulation.clock import get_open_markets, is_market_open

logger = structlog.get_logger()


class SimulationEngine:
    """Main simulation loop — creates agents, runs LangGraph cycles.

    System only provides structure and tools. All decisions (strategy,
    organization, trading, hiring, firing) are made by agents autonomously.
    """

    def __init__(
        self,
        *,
        symbols: list[str] | None = None,
    ) -> None:
        self._symbols = symbols
        self._agents: list[BaseAgent] = []
        self._running = False
        self._cycle_count = 0

        # Adapters (initialized in start())
        self._llm = None
        self._trading = None
        self._market_data = None
        self._recorder = None

    def _init_adapters(self) -> None:
        """Initialize all adapters and tracing from settings."""
        setup_tracing()
        from agentic_capital.adapters.kis_session import KISSession
        from agentic_capital.adapters.llm.gemini import GeminiLLMAdapter
        from agentic_capital.adapters.trading.kis import KISTradingAdapter

        self._llm = GeminiLLMAdapter()
        kis_session = KISSession()
        self._trading = KISTradingAdapter(session=kis_session)
        from agentic_capital.adapters.market_data.yfinance_adapter import YFinanceMarketDataAdapter
        self._market_data = YFinanceMarketDataAdapter()
        logger.info("adapters_initialized")

    def _init_agents(self) -> None:
        """Create initial agent roster — temporary, AI changes everything."""
        seed = settings.simulation_seed

        # Initial organization: CEO + Analyst + Trader (temporary — CEO changes as needed)
        self._agents = [
            create_agent(
                role="ceo",
                name="CEO-Alpha",
                philosophy="Maximize fund returns through optimal organization and strategy",
                seed=seed,
                llm=self._llm,
            ),
            create_agent(
                role="analyst",
                name="Analyst-Beta",
                philosophy="Data-driven market analysis for maximum signal accuracy",
                seed=seed + 1,
                llm=self._llm,
            ),
            create_agent(
                role="trader",
                name="Trader-Gamma",
                philosophy="Execute trades with precision — high conviction, strict risk management",
                seed=seed + 2,
                llm=self._llm,
                trading=self._trading,
            ),
        ]

        logger.info("agents_initialized", count=len(self._agents))
        for agent in self._agents:
            logger.info(
                "agent_created",
                name=agent.name,
                role=type(agent).__name__,
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
                    "agents": [a.name for a in self._agents],
                },
            )

            for agent in self._agents:
                await self._recorder.record_agent(
                    agent_id=agent.agent_id,
                    name=agent.name,
                    role=type(agent).__name__,
                    philosophy=agent.profile.philosophy,
                    personality=agent.personality,
                )

            await self._recorder.commit()
            logger.info("recorder_initialized", simulation_id=str(sim_id))
        except Exception:
            logger.warning("recorder_init_failed_running_without_db")
            self._recorder = None

    async def start(self) -> None:
        """Start the simulation loop.

        Agents control their own timing via request_wakeup().
        System only provides trade execution — agents decide everything else.
        """
        logger.info(
            "simulation_starting",
            initial_capital=settings.initial_capital,
            seed=settings.simulation_seed,
        )

        self._init_adapters()
        self._init_agents()

        await self._init_recorder()

        balance = await self._trading.get_balance()
        logger.info(
            "initial_state",
            balance_total=balance.total,
            balance_available=balance.available,
            currency=balance.currency,
        )

        self._running = True
        try:
            while self._running:
                next_delay = await self._run_cycle()

                if self._running and next_delay > 0:
                    logger.info(
                        "cycle_sleeping",
                        next_cycle_in=f"{next_delay}s",
                        total_cycles=self._cycle_count,
                    )
                    await asyncio.sleep(next_delay)
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

    async def _run_cycle(self) -> int:
        """Run one complete cycle for all agents using LangGraph.

        Returns minimum next_cycle_seconds across all agents (0 = run immediately).
        Agents control timing via request_wakeup() tool.
        """
        self._cycle_count += 1
        market_open = is_market_open()
        open_markets = get_open_markets()
        logger.info("cycle_start", cycle=self._cycle_count, market_open=market_open, open_markets=open_markets)

        # Run each agent through LangGraph workflow
        cycle_results = []
        for agent in list(self._agents):  # Copy list — any agent might modify roster
            try:
                result = await run_agent_cycle(
                    agent,
                    cycle_number=self._cycle_count,
                    trading=self._trading,
                    market_data=self._market_data,
                    open_markets=open_markets,
                    recorder=self._recorder,
                )
                cycle_results.append(result)

                # Process organizational actions — any agent can propose
                await self._process_org_actions(agent, result)

            except Exception:
                logger.exception("agent_cycle_failed", agent=agent.name, cycle=self._cycle_count)

        # Record company snapshot
        if self._recorder and self._trading:
            try:
                balance = await self._trading.get_balance()
                await self._recorder.record_company_snapshot(
                    total_capital=balance.total,
                    available_cash=balance.available,
                    agents_count=len(self._agents),
                    org_snapshot={
                        "agents": [
                            {"id": str(a.agent_id), "name": a.name, "role": type(a).__name__}
                            for a in self._agents
                        ],
                    },
                )
                await self._recorder.commit()
            except Exception:
                logger.exception("snapshot_recording_failed")

        # Collect agent-requested delays — use minimum (most urgent wins)
        delays = [r.get("next_cycle_seconds", 0) for r in cycle_results if r]
        next_delay = min(delays) if delays else 0

        logger.info(
            "cycle_complete",
            cycle=self._cycle_count,
            agents_count=len(self._agents),
            total_decisions=sum(len(r.get("decisions", [])) for r in cycle_results),
            next_cycle_in=f"{next_delay}s",
        )

        return next_delay

    async def _process_org_actions(self, agent: BaseAgent, result: dict) -> None:
        """Process organizational actions from any agent's decisions.

        Any agent can propose org actions — AI decides who has authority.
        System executes what agents decide and records everything.
        """
        for decision in result.get("decisions", []):
            if not isinstance(decision, dict):
                continue

            action_type = decision.get("type", decision.get("action_type", ""))

            if action_type == "hire":
                await self._handle_hire(agent, decision)
            elif action_type == "fire":
                await self._handle_fire(agent, decision)
            elif action_type == "create_role":
                await self._handle_create_role(agent, decision)
            elif action_type == "abolish_role":
                await self._handle_abolish_role(agent, decision)

    async def _handle_hire(self, ceo: BaseAgent, decision: dict) -> None:
        """Execute a hire decision — create new agent."""
        role = decision.get("detail", decision.get("role", "trader")).lower()
        name = decision.get("target", f"Agent-{len(self._agents) + 1}")
        capital = float(decision.get("capital", 0))
        personality_spec = decision.get("personality", {})

        try:
            # Use personality spec from CEO if provided, else random
            personality = None
            if personality_spec:
                from agentic_capital.core.personality.models import PersonalityVector
                personality = PersonalityVector(**{
                    k: float(v) for k, v in personality_spec.items()
                    if k in PersonalityVector.model_fields
                })

            # CEO decides the role — system accepts any role name
            kwargs = {"role": role, "name": name, "llm": self._llm, "personality": personality}
            if role.lower() == "trader":
                kwargs["trading"] = self._trading

            new_agent = create_agent(
                allocated_capital=capital,
                **kwargs,
            )
            self._agents.append(new_agent)

            # Record
            if self._recorder:
                await self._recorder.record_agent(
                    agent_id=new_agent.agent_id,
                    name=new_agent.name,
                    role=role,
                    philosophy=new_agent.profile.philosophy,
                    personality=new_agent.personality,
                )
                from agentic_capital.core.organization.hr import HREvent, HREventType
                await self._recorder.record_hr_event(HREvent(
                    event_type=HREventType.HIRE,
                    target_agent_id=new_agent.agent_id,
                    decided_by=ceo.agent_id,
                    reasoning=decision.get("reason", ""),
                    new_capital=capital,
                ))

            logger.info("agent_hired", name=name, role=role, hired_by=ceo.name)

        except Exception:
            logger.exception("hire_failed", name=name)

    async def _handle_fire(self, ceo: BaseAgent, decision: dict) -> None:
        """Execute a fire decision — remove agent from roster."""
        target = decision.get("target", "")

        # Find agent by name or ID
        agent_to_fire = None
        for a in self._agents:
            if a.name == target or str(a.agent_id) == target:
                agent_to_fire = a
                break

        if not agent_to_fire or agent_to_fire is ceo:
            return  # Can't fire self or nonexistent agent

        self._agents.remove(agent_to_fire)

        if self._recorder:
            from agentic_capital.core.organization.hr import HREvent, HREventType
            await self._recorder.record_hr_event(HREvent(
                event_type=HREventType.FIRE,
                target_agent_id=agent_to_fire.agent_id,
                decided_by=ceo.agent_id,
                reasoning=decision.get("reason", ""),
            ))
            await self._recorder.record_agent_status_change(
                agent_id=agent_to_fire.agent_id,
                new_status="fired",
                reason=decision.get("reason", ""),
            )

        logger.info("agent_fired", name=agent_to_fire.name, fired_by=ceo.name)

    async def _handle_create_role(self, ceo: BaseAgent, decision: dict) -> None:
        """Execute a create_role decision."""
        role_name = decision.get("detail", decision.get("target", ""))
        if not role_name:
            return

        if self._recorder:
            await self._recorder.record_role(
                role_name=role_name,
                permissions=decision.get("permissions", []),
                created_by=ceo.agent_id,
            )

        logger.info("role_created", name=role_name, created_by=ceo.name)

    async def _handle_abolish_role(self, ceo: BaseAgent, decision: dict) -> None:
        """Execute an abolish_role decision."""
        role_name = decision.get("detail", decision.get("target", ""))
        if not role_name:
            return

        if self._recorder:
            await self._recorder.record_role(
                role_name=role_name,
                created_by=ceo.agent_id,
                status="abolished",
            )

        logger.info("role_abolished", name=role_name, abolished_by=ceo.name)
