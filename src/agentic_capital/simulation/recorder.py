"""Simulation recorder — persist all decisions, trades, and state to DB."""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_capital.core.decision.pipeline import TradingDecision
from agentic_capital.core.personality.models import EmotionState, PersonalityVector
from agentic_capital.infra.models.agent import (
    AgentDecisionModel,
    AgentEmotionHistoryModel,
    AgentModel,
    AgentPersonalityHistoryModel,
    AgentPersonalityModel,
)
from agentic_capital.infra.models.simulation import CompanySnapshotModel, SimulationRunModel
from agentic_capital.infra.models.trade import TradeModel

logger = structlog.get_logger()


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
        decision: TradingDecision,
        personality: PersonalityVector,
        emotion: EmotionState,
        status: str,
        price: float = 0.0,
    ) -> None:
        """Record a trading decision and its execution result."""
        decision_record = AgentDecisionModel(
            agent_id=agent_id,
            simulation_id=self._simulation_id,
            decision_type="trade",
            action=f"{decision.action} {decision.symbol} x{decision.quantity}",
            reasoning=decision.reason,
            confidence=decision.confidence,
            personality_snapshot=_personality_to_dict(personality),
            emotion_snapshot=_emotion_to_dict(emotion),
            context_snapshot={},
            outcome={"status": status, "price": price},
        )
        self._session.add(decision_record)

        if status in ("submitted", "filled") and decision.action != "HOLD":
            trade = TradeModel(
                simulation_id=self._simulation_id,
                agent_id=agent_id,
                market="kr_stock",
                symbol=decision.symbol,
                side=decision.action.lower(),
                order_type="limit",
                quantity=decision.quantity,
                price=price,
                total_value=price * decision.quantity,
                thesis=decision.reason,
                confidence=decision.confidence,
                personality_snapshot=_personality_to_dict(personality),
                emotion_snapshot=_emotion_to_dict(emotion),
                status=status,
            )
            self._session.add(trade)

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
    ) -> None:
        """Record company-wide metrics snapshot."""
        snapshot = CompanySnapshotModel(
            time=datetime.now(),
            simulation_id=self._simulation_id,
            total_capital=total_capital,
            allocated_capital=total_capital - available_cash,
            cash=available_cash,
            agents_count=agents_count,
            daily_pnl_pct=daily_pnl_pct,
        )
        self._session.add(snapshot)
        await self._session.flush()

    async def end_simulation(self, status: str = "completed") -> None:
        """Mark simulation as ended."""
        if self._simulation_id:
            from sqlalchemy import update
            stmt = update(SimulationRunModel).where(
                SimulationRunModel.id == self._simulation_id
            ).values(ended_at=datetime.now(), status=status)
            await self._session.execute(stmt)
            await self._session.flush()

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
