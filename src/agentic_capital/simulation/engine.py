"""Simulation engine — LangGraph-based autonomous multi-agent loop.

System provides the structure and records everything.
Agents decide everything autonomously. Only constraint: capital.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import structlog

from agentic_capital.config import settings
from agentic_capital.core.agents.factory import create_agent
from agentic_capital.core.organization.audit import audit_roster
from agentic_capital.graph.workflow import run_agent_cycle
from agentic_capital.infra.tracing import setup_tracing
from agentic_capital.simulation.clock import get_open_markets, is_market_open

if TYPE_CHECKING:
    from agentic_capital.core.agents.base import BaseAgent

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
        self._stop_diagnostics: dict | None = None

    def _validate_startup_gate(self) -> None:
        """Block paper trading unless the finance local LLM is ready."""
        from agentic_capital.adapters.llm.router import is_local_llm_enabled

        if (
            is_local_llm_enabled()
            and settings.local_llm_model.strip().lower().startswith("finance_")
            and not settings.local_agent_llm_base_url.strip()
        ):
            raise RuntimeError(
                "LOCAL_AGENT_LLM_BASE_URL is required so CEO/Analyst do not use the finance sidecar as a general LLM"
            )
        if not is_local_llm_enabled() and not settings.local_finance_pipeline_enabled:
            return
        from agentic_capital.adapters.llm.local_finance_runtime import validate_local_finance_runtime

        validate_local_finance_runtime()

    def _init_adapters(self) -> None:
        """Initialize all adapters and tracing from settings."""
        self._validate_startup_gate()
        setup_tracing()
        from agentic_capital.adapters.kis_session import KISSession
        from agentic_capital.adapters.llm.router import build_llm_adapter
        from agentic_capital.adapters.trading.futures_virtual import FuturesVirtualAdapter
        from agentic_capital.adapters.trading.kis import KISTradingAdapter

        self._llm = build_llm_adapter()
        kis_session = KISSession()
        trading = KISTradingAdapter(session=kis_session)
        if settings.kis_is_paper and settings.futures_virtual_paper_fallback:
            trading = FuturesVirtualAdapter(trading, initial_capital=self._capital_limit)
        self._trading = trading
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
        session = None
        try:
            from agentic_capital.adapters.llm.router import llm_run_metadata
            from agentic_capital.infra.database import async_session
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
                    "agent_llm_base_url": metadata.get("agent_llm_base_url"),
                },
                llm_model=metadata["llm_model"],
                embedding_model=metadata["embedding_model"],
            )

            for agent in self._agents:
                await self._recorder.record_agent(
                    agent_id=agent.agent_id,
                    name=agent.name,
                    role=agent.role,
                    philosophy=agent.profile.philosophy,
                    personality=agent.personality,
                    allocated_capital=agent.profile.allocated_capital,
                )

            await self._recorder.commit()
            logger.info("recorder_initialized", simulation_id=str(sim_id))
        except Exception as exc:
            if session is not None:
                try:
                    await session.rollback()
                    await session.close()
                except Exception:
                    logger.exception("recorder_init_cleanup_failed")
            self._recorder = None
            logger.exception("recorder_init_failed")
            raise RuntimeError(
                "recorder initialization failed; refusing to run paper loop without DB recording"
            ) from exc

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
        runtime_health: dict | None = None
        if settings.local_runtime_healthcheck_enabled:
            try:
                from agentic_capital.monitoring.runtime_health import collect_runtime_health

                runtime_health = await collect_runtime_health()
            except Exception:
                logger.exception("runtime_health_check_failed", cycle=self._cycle_count)

        # Run each agent through LangGraph workflow
        cycle_results = []
        for agent in list(self._agents):  # Copy list — any agent might modify roster
            try:
                result = await run_agent_cycle(
                    agent,
                    cycle_number=self._cycle_count,
                    trading=self._trading,
                    market_data=self._market_data,
                    symbols=self._symbols,
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
                positions = await self._trading.get_positions()
                effective_total = min(float(balance.total), self._capital_limit)
                allocated_capital = min(
                    effective_total,
                    sum(
                        max(0.0, float(getattr(pos, "quantity", 0.0)))
                        * max(0.0, float(getattr(pos, "current_price", getattr(pos, "avg_price", 0.0)) or 0.0))
                        for pos in positions
                    ),
                )
                available_cash = max(0.0, effective_total - allocated_capital)
                await self._recorder.record_company_snapshot(
                    total_capital=effective_total,
                    available_cash=available_cash,
                    agents_count=len(self._agents),
                    org_snapshot={
                        "agents": audit_roster(self._agents)["active_agents"],
                        "organization_health": audit_roster(self._agents),
                        "broker_balance": {
                            "total": balance.total,
                            "available": balance.available,
                            "currency": balance.currency,
                        },
                        "paper_allocated_capital": allocated_capital,
                        "runtime_health": runtime_health,
                    },
                )
                await self._recorder.commit()
            except Exception:
                logger.exception("snapshot_recording_failed")

        # Keep recorder positions aligned with broker/KIS after any paper order
        # submitted during the cycle. The reconciliation path is read-only
        # against the broker and records snapshots only; it never submits orders.
        await self._reconcile_with_broker()

        # Collect agent-requested delays — use minimum (most urgent wins)
        delays = [r.get("next_cycle_seconds", 0) for r in cycle_results if r]
        requested_delay = min(delays) if delays else 0
        total_decisions = sum(len(r.get("decisions", [])) for r in cycle_results)
        self._log_finance_failures_before_guards(cycle_results)
        guard_context = self._classify_guard_context(cycle_results)
        next_delay = self._apply_cycle_guards(
            requested_delay=requested_delay,
            total_decisions=total_decisions,
            guard_context=guard_context,
        )

        logger.info(
            "cycle_complete",
            cycle=self._cycle_count,
            agents_count=len(self._agents),
            total_decisions=total_decisions,
            next_cycle_in=f"{next_delay}s",
            zero_decision_streak=self._zero_decision_streak,
            stop_diagnostics=self._stop_diagnostics,
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
                "first_failing_stage": result.get("first_failing_stage")
                or ((result.get("finance_record") or {}).get("details") or {}).get("first_failing_stage"),
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

    def _classify_guard_context(self, cycle_results: list[dict]) -> dict:
        """Classify no-decision failures for stop diagnostics."""
        for result in cycle_results:
            if not result or not result.get("finance_no_context"):
                continue
            record = result.get("finance_record") if isinstance(result.get("finance_record"), dict) else {}
            details = record.get("details") if isinstance(record.get("details"), dict) else {}
            first_failing_stage = result.get("first_failing_stage") or details.get("first_failing_stage")
            return {
                "cause_classification": "finance_sidecar_no_context",
                "first_failing_stage": first_failing_stage,
                "failure_type": record.get("failure_type"),
                "agent": result.get("agent_name"),
            }
        for result in cycle_results:
            if not result or not result.get("errors"):
                continue
            errors = result.get("errors") if isinstance(result.get("errors"), list) else []
            first_error = str(errors[0]) if errors else "unknown_agent_error"
            first_failing_stage = result.get("first_failing_stage")
            if not first_failing_stage:
                normalized = first_error.lower()
                if "timeout" in normalized or "readtimeout" in normalized or first_error == "TimeoutError":
                    first_failing_stage = "local_agent_runtime_timeout"
                elif "connect" in normalized or "connection" in normalized:
                    first_failing_stage = "local_agent_runtime_connection"
                else:
                    first_failing_stage = "local_agent_runtime"
            return {
                "cause_classification": "local_agent_runtime_failure",
                "first_failing_stage": first_failing_stage,
                "failure_type": first_error[:160],
                "agent": result.get("agent_name"),
            }
        return {"cause_classification": "agent_no_decision"}

    def _apply_cycle_guards(
        self,
        *,
        requested_delay: int | float | None,
        total_decisions: int,
        guard_context: dict | None = None,
    ) -> int:
        """Clamp unsafe pacing and stop repeated no-decision loops."""
        max_zero_cycles = max(int(settings.simulation_zero_decision_max_cycles), 0)
        if total_decisions <= 0:
            self._zero_decision_streak += 1
        else:
            self._zero_decision_streak = 0

        if max_zero_cycles and self._zero_decision_streak >= max_zero_cycles:
            self._stop_reason = "zero_decision_guard"
            self._stop_diagnostics = {
                "stop_reason": self._stop_reason,
                "streak": self._zero_decision_streak,
                "max_cycles": max_zero_cycles,
                **(guard_context or {}),
            }
            self._running = False
            logger.warning(
                "zero_decision_guard_triggered",
                streak=self._zero_decision_streak,
                max_cycles=max_zero_cycles,
                stop_diagnostics=self._stop_diagnostics,
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
        seen_hires: set[tuple[str, str]] = set()
        for decision in result.get("decisions", []):
            if not isinstance(decision, dict):
                continue

            action_type = decision.get("type", decision.get("action_type", ""))

            if action_type == "hire":
                hire_key = (
                    str(decision.get("target", "")).strip().lower(),
                    str(decision.get("detail", decision.get("role", "trader"))).strip().lower(),
                )
                if hire_key in seen_hires:
                    logger.warning(
                        "duplicate_hire_decision_skipped",
                        agent=agent.name,
                        target=decision.get("target"),
                        role=decision.get("detail", decision.get("role", "trader")),
                    )
                    continue
                seen_hires.add(hire_key)
                await self._handle_hire(agent, decision)
            elif action_type == "fire":
                await self._handle_fire(agent, decision)
            elif action_type == "create_role":
                await self._handle_create_role(agent, decision)
            elif action_type == "abolish_role":
                await self._handle_abolish_role(agent, decision)

    async def _handle_hire(self, ceo: BaseAgent, decision: dict) -> None:
        """Execute a hire decision — create new agent."""
        role = str(decision.get("detail", decision.get("role", "trader")) or "trader").strip().lower()
        base_name = str(decision.get("target", f"Agent-{len(self._agents) + 1}") or "").strip()
        if not base_name:
            base_name = f"Agent-{len(self._agents) + 1}"
        requested_capital = max(0.0, float(decision.get("capital", 0) or 0.0))
        capital = min(requested_capital, max(0.0, self._capital_limit))
        philosophy = str(decision.get("philosophy") or decision.get("reason") or "")
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
                philosophy=philosophy,
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
                    allocated_capital=capital,
                    created_by=ceo.agent_id,
                )
                from agentic_capital.core.organization.hr import HREvent, HREventType
                await self._recorder.record_hr_event(HREvent(
                    event_type=HREventType.HIRE,
                    target_agent_id=new_agent.agent_id,
                    decided_by=ceo.agent_id,
                    reasoning=decision.get("reason", ""),
                    new_capital=capital,
                    context_snapshot={
                        "requested_capital": requested_capital,
                        "allocated_capital": capital,
                        "role": role,
                        "name": name,
                    },
                ))

            logger.info(
                "agent_hired",
                name=name,
                role=role,
                hired_by=ceo.name,
                requested_capital=requested_capital,
                allocated_capital=capital,
            )

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
            logger.warning(
                "agent_fire_skipped",
                target=target,
                decided_by=ceo.name,
                reason="self_or_missing_agent",
            )
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
        """Reconcile DB positions with real broker account.

        Fetches the current real positions from KIS and records them as a
        reconciliation snapshot so agents use accurate ground truth.
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
            real_by_position = {
                (str(getattr(p, "market", "kr_stock")), p.symbol): p
                for p in real_positions
            }
            db_by_position = {
                (str(p.get("market", "kr_stock")), p["symbol"]): p
                for p in db_positions
            }

            discrepancies: list[dict] = []

            # Check for positions in real account missing or different from DB
            for (market, symbol), real_pos in real_by_position.items():
                db_pos = db_by_position.get((market, symbol))
                if db_pos is None:
                    discrepancies.append({
                        "symbol": symbol,
                        "market": market,
                        "issue": "missing_in_db",
                        "real_qty": real_pos.quantity,
                        "db_qty": 0,
                    })
                elif abs(float(db_pos.get("quantity", 0)) - real_pos.quantity) > 0.001:
                    discrepancies.append({
                        "symbol": symbol,
                        "market": market,
                        "issue": "qty_mismatch",
                        "real_qty": real_pos.quantity,
                        "db_qty": db_pos.get("quantity", 0),
                    })

            # Check for positions in DB that no longer exist in real account
            for (market, symbol), db_pos in db_by_position.items():
                if (market, symbol) not in real_by_position:
                    discrepancies.append({
                        "symbol": symbol,
                        "market": market,
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
                logger.info("position_reconciliation_ok", positions=len(real_by_position))

            # Resolve position owner per symbol:
            # - use the agent who last traded that symbol (if still active)
            # - fall back to any active agent if original trader is gone
            active_ids = {a.agent_id for a in self._agents}
            fallback_id = self._agents[0].agent_id if self._agents else None

            for (market, symbol), db_pos in db_by_position.items():
                if (market, symbol) in real_by_position:
                    continue
                owner_id = await self._recorder.get_position_owner(symbol, active_ids)
                if owner_id is None:
                    owner_id = fallback_id
                if owner_id is None:
                    logger.warning(
                        "closed_position_snapshot_skipped_no_owner",
                        symbol=symbol,
                        market=market,
                    )
                    continue
                await self._recorder.record_position_snapshot(
                    agent_id=owner_id,
                    symbol=symbol,
                    quantity=0.0,
                    avg_price=float(db_pos.get("avg_price", 0.0)),
                    unrealized_pnl=0.0,
                    unrealized_pnl_pct=0.0,
                    market=market,
                )

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
