"""Simulation recorder — persist ALL agent states, actions, and results to DB.

Every persona's every action, state change, and result is recorded.
No exceptions. Roles, permissions, messages, decisions, emotions, positions — everything.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_capital.core.communication.protocol import AgentMessage
from agentic_capital.core.decision.pipeline import TradingDecision
from agentic_capital.core.organization.hr import HREvent
from agentic_capital.core.personality.models import EmotionState, PersonalityVector
from agentic_capital.infra.models.agent import (
    AgentDecisionModel,
    AgentEmotionHistoryModel,
    AgentModel,
    AgentPersonalityHistoryModel,
    AgentPersonalityModel,
)
from agentic_capital.infra.models.organization import (
    AgentMessageModel,
    HREventModel,
    PermissionHistoryModel,
    RoleModel,
)
from agentic_capital.infra.models.simulation import CompanySnapshotModel, SimulationRunModel
from agentic_capital.infra.models.tool import AgentToolModel
from agentic_capital.infra.models.trade import PositionModel, TradeModel

logger = structlog.get_logger()

# KIS commission rates (estimated, paper trading does not deduct actual fees)
_COMMISSION_RATES: dict[str, float] = {
    "kr_stock": 0.00015,   # 0.015% domestic stock
    "kr_futures": 0.00005, # 0.005% domestic futures
    "kr_options": 0.00005,
    "us_stock": 0.0025,    # 0.25% overseas stock
    "hk_stock": 0.0025,
    "cn_stock": 0.0025,
    "jp_stock": 0.0025,
    "vn_stock": 0.0025,
}


def _estimate_commission(market: str, total_value: float) -> float:
    """Estimate trading commission. AI uses this for P&L awareness."""
    rate = _COMMISSION_RATES.get(market, 0.00015)
    return round(total_value * rate, 4)


class SimulationRecorder:
    """Records all simulation events to PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._simulation_id: uuid.UUID | None = None

    async def start_simulation(
        self,
        seed: int,
        initial_capital: float,
        config: dict,
    ) -> uuid.UUID:
        """Create a simulation run record."""
        sim_id = uuid.uuid4()
        run = SimulationRunModel(
            id=sim_id,
            seed=seed,
            llm_model="gemini-2.5-flash",
            embedding_model="text-embedding-004",
            config=config,
            initial_capital=initial_capital,
            status="running",
        )
        self._session.add(run)
        await self._session.flush()
        self._simulation_id = sim_id
        logger.info("simulation_recorded", simulation_id=str(sim_id))
        return sim_id

    async def record_agent(
        self,
        agent_id: uuid.UUID,
        name: str,
        role: str,
        philosophy: str,
        personality: PersonalityVector,
    ) -> None:
        """Record agent creation."""
        agent = AgentModel(
            id=agent_id,
            simulation_id=self._simulation_id,
            name=name,
            status="active",
            philosophy=philosophy,
        )
        self._session.add(agent)

        p = AgentPersonalityModel(
            agent_id=agent_id,
            openness=personality.openness,
            conscientiousness=personality.conscientiousness,
            extraversion=personality.extraversion,
            agreeableness=personality.agreeableness,
            neuroticism=personality.neuroticism,
            honesty_humility=personality.honesty_humility,
            loss_aversion=personality.loss_aversion,
            risk_aversion_gains=personality.risk_aversion_gains,
            risk_aversion_losses=personality.risk_aversion_losses,
            probability_weighting=personality.probability_weighting,
        )
        self._session.add(p)
        await self._session.flush()

    async def record_decision(
        self,
        agent_id: uuid.UUID,
        decision: TradingDecision | None = None,
        personality: PersonalityVector | None = None,
        emotion: EmotionState | None = None,
        status: str = "",
        price: float = 0.0,
        market: str = "kr_stock",
        *,
        decision_type: str = "trade",
        action: str = "",
        reasoning: str = "",
        confidence: float = 0.5,
        context_snapshot: dict | None = None,
        outcome: dict | None = None,
    ) -> None:
        """Record any agent decision — trade, HR, strategy, reorg, or any other type.

        Supports both TradingDecision objects and generic decisions via kwargs.
        """
        p_snap = _personality_to_dict(personality) if personality else {}
        e_snap = _emotion_to_dict(emotion) if emotion else {}

        if decision is not None:
            # TradingDecision path
            decision_record = AgentDecisionModel(
                agent_id=agent_id,
                simulation_id=self._simulation_id,
                decision_type=decision_type,
                action=f"{decision.action} {decision.symbol} x{decision.quantity}",
                reasoning=decision.reason,
                confidence=decision.confidence,
                personality_snapshot=p_snap,
                emotion_snapshot=e_snap,
                context_snapshot=context_snapshot or {},
                outcome=outcome or {"status": status, "price": price},
            )
            self._session.add(decision_record)

            if status in ("submitted", "filled") and decision.action != "HOLD":
                total_val = price * decision.quantity
                commission = _estimate_commission(market, total_val)
                side_sign = -1 if decision.action.upper() == "BUY" else 1
                net_val = total_val + side_sign * commission  # buy: cost+fee, sell: proceeds-fee
                trade = TradeModel(
                    simulation_id=self._simulation_id,
                    agent_id=agent_id,
                    market=market,
                    symbol=decision.symbol,
                    side=decision.action.lower(),
                    order_type="limit" if price > 0 else "market",
                    quantity=decision.quantity,
                    price=price,
                    total_value=total_val,
                    commission=commission,
                    net_value=net_val,
                    thesis=decision.reason,
                    confidence=decision.confidence,
                    personality_snapshot=p_snap,
                    emotion_snapshot=e_snap,
                    status=status,
                )
                self._session.add(trade)
        else:
            # Generic decision path (HR, strategy, reorg, etc.)
            decision_record = AgentDecisionModel(
                agent_id=agent_id,
                simulation_id=self._simulation_id,
                decision_type=decision_type,
                action=action,
                reasoning=reasoning,
                confidence=confidence,
                personality_snapshot=p_snap,
                emotion_snapshot=e_snap,
                context_snapshot=context_snapshot or {},
                outcome=outcome,
            )
            self._session.add(decision_record)

        await self._session.flush()

    async def record_emotion(
        self,
        agent_id: uuid.UUID,
        emotion: EmotionState,
        trigger: str = "",
    ) -> None:
        """Record emotion state change."""
        record = AgentEmotionHistoryModel(
            time=datetime.now(),
            agent_id=agent_id,
            valence=emotion.valence,
            arousal=emotion.arousal,
            dominance=emotion.dominance,
            stress=emotion.stress,
            confidence=emotion.confidence,
            trigger=trigger,
        )
        self._session.add(record)
        await self._session.flush()

    async def record_personality_drift(
        self,
        agent_id: uuid.UUID,
        drift_events: list[tuple[str, float, float]],
        trigger: str = "",
    ) -> None:
        """Record personality parameter changes."""
        now = datetime.now()
        for param, old_val, new_val in drift_events:
            record = AgentPersonalityHistoryModel(
                time=now,
                agent_id=agent_id,
                parameter=param,
                old_value=old_val,
                new_value=new_val,
                trigger_event=trigger,
            )
            self._session.add(record)
        if drift_events:
            await self._session.flush()

    async def record_company_snapshot(
        self,
        total_capital: float,
        available_cash: float,
        agents_count: int,
        daily_pnl_pct: float = 0.0,
        cumulative_pnl_pct: float = 0.0,
        sharpe_30d: float | None = None,
        max_drawdown_pct: float | None = None,
        org_snapshot: dict | None = None,
    ) -> None:
        """Record company-wide metrics snapshot with full performance data."""
        snapshot = CompanySnapshotModel(
            time=datetime.now(),
            simulation_id=self._simulation_id,
            total_capital=total_capital,
            allocated_capital=total_capital - available_cash,
            cash=available_cash,
            agents_count=agents_count,
            daily_pnl_pct=daily_pnl_pct,
            cumulative_pnl_pct=cumulative_pnl_pct,
            sharpe_30d=sharpe_30d,
            max_drawdown_pct=max_drawdown_pct,
            org_snapshot=org_snapshot or {},
        )
        self._session.add(snapshot)
        await self._session.flush()

    async def record_hr_event(self, hr_event: HREvent) -> None:
        """Record any HR event — hire, fire, promote, demote, role_change, reward, warn."""
        record = HREventModel(
            simulation_id=self._simulation_id,
            event_type=str(hr_event.event_type),
            target_agent_id=hr_event.target_agent_id,
            decided_by=hr_event.decided_by,
            old_role_id=hr_event.old_role_id,
            new_role_id=hr_event.new_role_id,
            old_capital=hr_event.old_capital,
            new_capital=hr_event.new_capital,
            reasoning=hr_event.reasoning,
            context_snapshot=hr_event.context_snapshot,
        )
        self._session.add(record)
        await self._session.flush()
        logger.info(
            "hr_event_recorded",
            event_type=hr_event.event_type,
            target=str(hr_event.target_agent_id),
            decided_by=str(hr_event.decided_by),
        )

    async def record_agent_message(self, message: AgentMessage) -> None:
        """Record LACP protocol message to PostgreSQL for permanent storage."""
        record = AgentMessageModel(
            id=message.id,
            simulation_id=self._simulation_id,
            type=str(message.type),
            sender_id=message.sender_id,
            receiver_id=message.receiver_id,
            priority=message.priority,
            content=message.content,
            memory_refs=[str(ref) for ref in message.memory_refs],
            ttl=message.ttl,
        )
        self._session.add(record)
        await self._session.flush()

    async def record_position_snapshot(
        self,
        agent_id: uuid.UUID,
        symbol: str,
        quantity: float,
        avg_price: float,
        unrealized_pnl: float = 0.0,
        unrealized_pnl_pct: float = 0.0,
        market: str = "kr_stock",
    ) -> None:
        """Record position state for time-series tracking."""
        record = PositionModel(
            simulation_id=self._simulation_id,
            agent_id=agent_id,
            symbol=symbol,
            market=market,
            quantity=quantity,
            avg_price=avg_price,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            updated_at=datetime.now(),
        )
        self._session.add(record)
        await self._session.flush()

    async def record_role(
        self,
        role_name: str,
        permissions: list | None = None,
        report_to: uuid.UUID | None = None,
        created_by: uuid.UUID | None = None,
        status: str = "active",
    ) -> uuid.UUID:
        """Record role creation/modification. Returns role ID."""
        role_id = uuid.uuid4()
        record = RoleModel(
            id=role_id,
            simulation_id=self._simulation_id,
            name=role_name,
            permissions=permissions or [],
            report_to=report_to,
            created_by=created_by,
            status=status,
        )
        self._session.add(record)
        await self._session.flush()
        logger.info("role_recorded", role_id=str(role_id), name=role_name, status=status)
        return role_id

    async def record_permission_change(
        self,
        agent_id: uuid.UUID,
        action: str,
        changes: dict,
        decided_by: uuid.UUID,
        reasoning: str = "",
    ) -> None:
        """Record permission grant/revoke/modify events."""
        record = PermissionHistoryModel(
            time=datetime.now(),
            agent_id=agent_id,
            action=action,
            changes=changes,
            decided_by=decided_by,
            reasoning=reasoning,
        )
        self._session.add(record)
        await self._session.flush()

    async def record_agent_status_change(
        self,
        agent_id: uuid.UUID,
        new_status: str,
        reason: str = "",
    ) -> None:
        """Record agent status change (active → fired, retired, etc.)."""
        from sqlalchemy import update
        stmt = update(AgentModel).where(
            AgentModel.id == agent_id
        ).values(status=new_status)
        await self._session.execute(stmt)
        await self._session.flush()
        logger.info("agent_status_changed", agent_id=str(agent_id), status=new_status, reason=reason)

    async def end_simulation(self, status: str = "completed") -> None:
        """Mark simulation as ended."""
        if self._simulation_id:
            from sqlalchemy import update
            stmt = update(SimulationRunModel).where(
                SimulationRunModel.id == self._simulation_id
            ).values(ended_at=datetime.now(), status=status)
            await self._session.execute(stmt)
            await self._session.flush()

    async def save_tool(
        self,
        name: str,
        description: str,
        code: str,
        created_by: uuid.UUID | None = None,
    ) -> None:
        """Persist AI-created tool. Upserts by name so AI can iterate on tools."""
        from sqlalchemy import select, update as sa_update
        from agentic_capital.infra.models.tool import AgentToolModel

        existing = (
            await self._session.execute(
                select(AgentToolModel).where(AgentToolModel.name == name)
            )
        ).scalar_one_or_none()

        if existing:
            await self._session.execute(
                sa_update(AgentToolModel)
                .where(AgentToolModel.name == name)
                .values(description=description, code=code, status="active")
            )
        else:
            self._session.add(
                AgentToolModel(
                    name=name,
                    description=description,
                    code=code,
                    created_by=created_by,
                )
            )
        await self._session.flush()
        logger.info("agent_tool_saved", name=name, created_by=str(created_by))

    async def load_tools(self) -> list[dict]:
        """Load all active AI-created tools for injection into next cycle."""
        from sqlalchemy import select
        from agentic_capital.infra.models.tool import AgentToolModel

        result = await self._session.execute(
            select(AgentToolModel).where(AgentToolModel.status == "active")
        )
        return [
            {"name": t.name, "description": t.description, "code": t.code}
            for t in result.scalars().all()
        ]

    async def commit(self) -> None:
        """Commit all pending changes."""
        await self._session.commit()


def _personality_to_dict(p: PersonalityVector) -> dict:
    return {
        "openness": p.openness,
        "conscientiousness": p.conscientiousness,
        "extraversion": p.extraversion,
        "agreeableness": p.agreeableness,
        "neuroticism": p.neuroticism,
        "honesty_humility": p.honesty_humility,
        "loss_aversion": p.loss_aversion,
        "risk_aversion_gains": p.risk_aversion_gains,
        "risk_aversion_losses": p.risk_aversion_losses,
        "probability_weighting": p.probability_weighting,
    }


def _emotion_to_dict(e: EmotionState) -> dict:
    return {
        "valence": e.valence,
        "arousal": e.arousal,
        "dominance": e.dominance,
        "stress": e.stress,
        "confidence": e.confidence,
    }
