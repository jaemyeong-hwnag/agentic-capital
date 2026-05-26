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
        self._capital_limit: float = float(settings.initial_capital)
        self._zero_decision_streak = 0
        self._stop_reason: str | None = None

    def _validate_startup_gate(self) -> None:
        """Block paper trading unless the finance local LLM is ready."""
        from agentic_capital.adapters.llm.router import is_local_llm_enabled

        if not is_local_llm_enabled():
            return
        from agentic_capital.adapters.llm.local_finance_runtime import validate_local_finance_runtime

        validate_local_finance_runtime()

    def _init_adapters(self) -> None:
        """Initialize all adapters and tracing from settings."""
        self._validate_startup_gate()
        setup_tracing()
        from agentic_capital.adapters.kis_session import KISSession
        from agentic_capital.adapters.llm.router import build_llm_adapter
        from agentic_capital.adapters.trading.kis import KISTradingAdapter

        self._llm = build_llm_adapter()
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
            from agentic_capital.adapters.llm.router import llm_run_metadata
            from agentic_capital.simulation.recorder import SimulationRecorder

            session = async_session()
            self._recorder = SimulationRecorder(session)
            metadata = llm_run_metadata()
            sim_id = await self._recorder.start_simulation(
                seed=settings.simulation_seed,
                initial_capital=settings.initial_capital,
                config={
                    "agents": [a.name for a in self._agents],
                    "llm_provider": metadata["llm_provider"],
                    "llm_base_url": metadata.get("llm_base_url"),
                },
                llm_model=metadata["llm_model"],
                embedding_model=metadata["embedding_model"],
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
        # Effective capital = min(KIS account, ENV setting) — whichever is smaller
        self._capital_limit = min(balance.total, settings.initial_capital)
        logger.info(
            "initial_state",
            balance_total=balance.total,
            balance_available=balance.available,
            currency=balance.currency,
            capital_limit=self._capital_limit,
        )

        # Reconcile DB positions with real broker account
        await self._reconcile_with_broker()

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
            logger.info("simulation_stopped", total_cycles=self._cycle_count, reason=self._stop_reason)

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
                    capital_limit=self._capital_limit,
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
        requested_delay = min(delays) if delays else 0
        total_decisions = sum(len(r.get("decisions", [])) for r in cycle_results)
        self._log_finance_failures_before_guards(cycle_results)
        next_delay = self._apply_cycle_guards(requested_delay=requested_delay, total_decisions=total_decisions)

        logger.info(
            "cycle_complete",
            cycle=self._cycle_count,
            agents_count=len(self._agents),
            total_decisions=total_decisions,
            next_cycle_in=f"{next_delay}s",
            zero_decision_streak=self._zero_decision_streak,
        )

        return next_delay

    def _log_finance_failures_before_guards(self, cycle_results: list[dict]) -> None:
        """Surface no-context finance failures before zero-decision stopping logic."""
        failures = [
            {
                "agent": result.get("agent_name"),
                "failure_type": (result.get("finance_record") or {}).get("failure_type"),
                "evidence_ids": result.get("evidence_ids", []),
                "risk_flags": result.get("risk_flags", []),
                "sidecar_latency_ms": result.get("sidecar_latency_ms"),
            }
            for result in cycle_results
            if result and result.get("finance_no_context")
        ]
        if failures:
            logger.warning(
                "finance_raw_model_failures_recorded_before_zero_guard",
                cycle=self._cycle_count,
                count=len(failures),
                failures=failures,
            )

    def _apply_cycle_guards(self, *, requested_delay: int | float | None, total_decisions: int) -> int:
        """Clamp unsafe pacing and stop repeated no-decision loops."""
        max_zero_cycles = max(int(settings.simulation_zero_decision_max_cycles), 0)
        if total_decisions <= 0:
            self._zero_decision_streak += 1
        else:
            self._zero_decision_streak = 0

        if max_zero_cycles and self._zero_decision_streak >= max_zero_cycles:
            self._stop_reason = "zero_decision_guard"
            self._running = False
            logger.warning(
                "zero_decision_guard_triggered",
                streak=self._zero_decision_streak,
                max_cycles=max_zero_cycles,
            )

        try:
            delay = int(requested_delay or 0)
        except (TypeError, ValueError):
            delay = 0

        min_delay = max(int(settings.simulation_min_cycle_seconds), 1)
        if delay <= 0:
            if settings.simulation_stop_when_market_closed and not is_market_open():
                self._stop_reason = self._stop_reason or "market_closed_zero_delay"
                self._running = False
                logger.warning("cycle_pacing_market_closed_stop", requested_delay=delay)
                return 0
            logger.warning("cycle_pacing_clamped", requested_delay=delay, min_cycle_seconds=min_delay)
            return min_delay
        if delay < min_delay:
            logger.warning("cycle_pacing_clamped", requested_delay=delay, min_cycle_seconds=min_delay)
            return min_delay
        return delay

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
        base_name = decision.get("target", f"Agent-{len(self._agents) + 1}")
        capital = float(decision.get("capital", 0))
        personality_spec = decision.get("personality", {})

        # Deduplicate by name — append UUID suffix if name already taken
        existing_names = {a.name for a in self._agents}
        if base_name in existing_names:
            name = f"{base_name}-{str(uuid.uuid4())[:8]}"
            logger.info("agent_hire_name_conflict_renamed", original=base_name, renamed=name)
        else:
            name = base_name

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

    async def _reconcile_with_broker(self) -> None:
        """Reconcile DB positions with real broker account at startup.

        Fetches the current real positions from KIS and records them as a
        reconciliation snapshot so agents start with accurate ground truth.
        Logs any discrepancies between the last DB snapshot and real account.
        """
        if not self._trading or not self._recorder:
            return

        try:
            real_positions = await self._trading.get_positions()
            real_balance = await self._trading.get_balance()

            # Get last recorded positions from DB for comparison
            db_positions = await self._recorder.get_last_positions()

            # Build lookup dicts for comparison
            real_by_symbol = {p.symbol: p for p in real_positions}
            db_by_symbol = {p["symbol"]: p for p in db_positions}

            discrepancies: list[dict] = []

            # Check for positions in real account missing or different from DB
            for symbol, real_pos in real_by_symbol.items():
                db_pos = db_by_symbol.get(symbol)
                if db_pos is None:
                    discrepancies.append({
                        "symbol": symbol,
                        "issue": "missing_in_db",
                        "real_qty": real_pos.quantity,
                        "db_qty": 0,
                    })
                elif abs(float(db_pos.get("quantity", 0)) - real_pos.quantity) > 0.001:
                    discrepancies.append({
                        "symbol": symbol,
                        "issue": "qty_mismatch",
                        "real_qty": real_pos.quantity,
                        "db_qty": db_pos.get("quantity", 0),
                    })

            # Check for positions in DB that no longer exist in real account
            for symbol, db_pos in db_by_symbol.items():
                if symbol not in real_by_symbol:
                    discrepancies.append({
                        "symbol": symbol,
                        "issue": "closed_in_broker",
                        "real_qty": 0,
                        "db_qty": db_pos.get("quantity", 0),
                    })

            if discrepancies:
                logger.warning(
                    "position_reconciliation_discrepancies",
                    count=len(discrepancies),
                    discrepancies=discrepancies,
                )
            else:
                logger.info("position_reconciliation_ok", positions=len(real_by_symbol))

            # Resolve position owner per symbol:
            # - use the agent who last traded that symbol (if still active)
            # - fall back to any active agent if original trader is gone
            active_ids = {a.agent_id for a in self._agents}
            fallback_id = self._agents[0].agent_id if self._agents else None

            for pos in real_positions:
                owner_id = await self._recorder.get_position_owner(pos.symbol, active_ids)
                if owner_id is None:
                    owner_id = fallback_id
                    if fallback_id:
                        logger.info(
                            "position_owner_reassigned",
                            symbol=pos.symbol,
                            new_owner=str(fallback_id),
                        )
                await self._recorder.record_position_snapshot(
                    agent_id=owner_id,
                    symbol=pos.symbol,
                    quantity=pos.quantity,
                    avg_price=pos.avg_price,
                    unrealized_pnl=getattr(pos, "unrealized_pnl", 0.0),
                    unrealized_pnl_pct=getattr(pos, "unrealized_pnl_pct", 0.0),
                    market=getattr(pos, "market", "kr_stock"),
                )

            await self._recorder.commit()
            logger.info(
                "broker_reconciliation_complete",
                real_positions=len(real_positions),
                real_balance=real_balance.total,
                discrepancies=len(discrepancies),
            )

        except Exception:
            logger.exception("broker_reconciliation_failed")
