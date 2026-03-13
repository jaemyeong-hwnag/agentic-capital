"""Integration tests — real PostgreSQL CRUD for ORM models and A-MEM."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from agentic_capital.core.memory.amem import AMEMStore, MemoryNote
from agentic_capital.core.memory.episodic import EpisodicMemory
from agentic_capital.core.memory.semantic import SemanticMemory
from agentic_capital.infra.models.agent import AgentModel, AgentPersonalityModel
from agentic_capital.infra.models.simulation import SimulationRunModel
from agentic_capital.infra.models.trade import TradeModel


@pytest.mark.integration
class TestAgentCRUD:
    @pytest.mark.asyncio
    async def test_create_simulation_run(self, db_session, simulation_id: uuid.UUID) -> None:
        sim = SimulationRunModel(
            id=simulation_id,
            seed=42,
            llm_model="gemini-2.5-pro",
            initial_capital=1_000_000,
        )
        db_session.add(sim)
        await db_session.flush()
        assert sim.status == "running"

    @pytest.mark.asyncio
    async def test_create_agent(self, db_session, simulation_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        sim = SimulationRunModel(
            id=simulation_id, seed=42, llm_model="gemini-2.5-pro", initial_capital=1_000_000,
        )
        db_session.add(sim)
        await db_session.flush()

        agent = AgentModel(
            id=agent_id,
            simulation_id=simulation_id,
            name="Alpha Trader",
            allocated_capital=500_000,
        )
        db_session.add(agent)
        await db_session.flush()
        assert agent.name == "Alpha Trader"
        assert agent.status == "active"

    @pytest.mark.asyncio
    async def test_create_agent_personality(self, db_session, agent_id: uuid.UUID, simulation_id: uuid.UUID) -> None:
        sim = SimulationRunModel(
            id=simulation_id, seed=42, llm_model="gemini-2.5-pro", initial_capital=1_000_000,
        )
        db_session.add(sim)

        agent = AgentModel(id=agent_id, simulation_id=simulation_id, name="Test Agent")
        db_session.add(agent)
        await db_session.flush()

        personality = AgentPersonalityModel(
            agent_id=agent_id,
            openness=0.8,
            conscientiousness=0.3,
            loss_aversion=0.7,
        )
        db_session.add(personality)
        await db_session.flush()
        assert personality.openness == 0.8

    @pytest.mark.asyncio
    async def test_create_trade(self, db_session, simulation_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        sim = SimulationRunModel(
            id=simulation_id, seed=42, llm_model="gemini-2.5-pro", initial_capital=1_000_000,
        )
        db_session.add(sim)

        agent = AgentModel(id=agent_id, simulation_id=simulation_id, name="Trader")
        db_session.add(agent)
        await db_session.flush()

        trade = TradeModel(
            simulation_id=simulation_id,
            agent_id=agent_id,
            market="us_stock",
            symbol="AAPL",
            side="buy",
            quantity=100,
            price=150.50,
            total_value=15050.00,
            thesis="RSI divergence bullish signal",
            confidence=0.75,
        )
        db_session.add(trade)
        await db_session.flush()
        assert trade.symbol == "AAPL"
        assert trade.status == "filled"


@pytest.mark.integration
class TestAMEMIntegration:
    @pytest.mark.asyncio
    async def test_create_and_get_note(self, db_session, simulation_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        store = AMEMStore(db_session)
        note = MemoryNote(
            agent_id=agent_id,
            simulation_id=simulation_id,
            memory_type="episodic",
            context="AAPL showed RSI divergence at 34",
            keywords=["rsi", "aapl", "divergence"],
            tags=["technical", "bullish"],
            importance=0.8,
        )
        created = await store.create(note)
        assert created.id == note.id

        fetched = await store.get(note.id)
        assert fetched is not None
        assert fetched.context == "AAPL showed RSI divergence at 34"
        assert fetched.access_count == 1

    @pytest.mark.asyncio
    async def test_search_by_keywords(self, db_session, simulation_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        store = AMEMStore(db_session)

        note1 = MemoryNote(
            agent_id=agent_id, simulation_id=simulation_id,
            memory_type="episodic", context="AAPL RSI divergence",
            keywords=["rsi", "aapl"], q_value=0.9,
        )
        note2 = MemoryNote(
            agent_id=agent_id, simulation_id=simulation_id,
            memory_type="episodic", context="TSLA earnings beat",
            keywords=["earnings", "tsla"], q_value=0.7,
        )
        await store.create(note1)
        await store.create(note2)

        results = await store.search_by_keywords(agent_id, ["rsi"])
        assert len(results) >= 1
        assert any(n.context == "AAPL RSI divergence" for n in results)

    @pytest.mark.asyncio
    async def test_link_notes(self, db_session, simulation_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        store = AMEMStore(db_session)

        note1 = MemoryNote(
            agent_id=agent_id, simulation_id=simulation_id,
            memory_type="semantic", context="RSI is a momentum indicator",
            keywords=["rsi"],
        )
        note2 = MemoryNote(
            agent_id=agent_id, simulation_id=simulation_id,
            memory_type="episodic", context="Used RSI to buy AAPL successfully",
            keywords=["rsi", "aapl"],
        )
        await store.create(note1)
        await store.create(note2)

        await store.add_link(note1.id, note2.id)
        linked = await store.get_linked(note1.id)
        assert len(linked) == 1
        assert linked[0].id == note2.id

    @pytest.mark.asyncio
    async def test_decay(self, db_session, simulation_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        store = AMEMStore(db_session)

        low_q_note = MemoryNote(
            agent_id=agent_id, simulation_id=simulation_id,
            memory_type="episodic", context="Old unimportant memory",
            q_value=0.06,
        )
        high_q_note = MemoryNote(
            agent_id=agent_id, simulation_id=simulation_id,
            memory_type="episodic", context="Important recent memory",
            q_value=0.9,
        )
        await store.create(low_q_note)
        await store.create(high_q_note)

        decayed_count = await store.decay(agent_id, threshold=0.05)
        assert decayed_count >= 1  # low_q_note should be decayed

    @pytest.mark.asyncio
    async def test_update_q_value(self, db_session, simulation_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        store = AMEMStore(db_session)

        note = MemoryNote(
            agent_id=agent_id, simulation_id=simulation_id,
            memory_type="episodic", context="Test Q update",
            q_value=0.5,
        )
        await store.create(note)

        new_q = await store.update_q_value(note.id, 0.2)
        assert abs(new_q - 0.7) < 1e-6


@pytest.mark.integration
class TestSemanticMemoryIntegration:
    @pytest.mark.asyncio
    async def test_store_and_search(self, db_session, simulation_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        sem = SemanticMemory(db_session)

        await sem.store_knowledge(
            agent_id, simulation_id,
            "Tech stocks rally after Fed rate pauses",
            keywords=["fed", "tech", "rate_pause"],
            tags=["macro"],
            importance=0.8,
        )

        results = await sem.search(agent_id, keywords=["fed"])
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_top_knowledge(self, db_session, simulation_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        sem = SemanticMemory(db_session)

        for i in range(3):
            await sem.store_knowledge(
                agent_id, simulation_id,
                f"Knowledge #{i}",
                importance=0.5 + i * 0.1,
            )

        top = await sem.get_top_knowledge(agent_id, limit=2)
        assert len(top) == 2

    @pytest.mark.asyncio
    async def test_count(self, db_session, simulation_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        sem = SemanticMemory(db_session)

        await sem.store_knowledge(agent_id, simulation_id, "Test knowledge 1")
        await sem.store_knowledge(agent_id, simulation_id, "Test knowledge 2")

        count = await sem.count(agent_id)
        assert count == 2


@pytest.mark.integration
class TestEpisodicMemoryIntegration:
    @pytest.mark.asyncio
    async def test_store_experience(self, db_session, simulation_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        epi = EpisodicMemory(db_session)

        note = await epi.store_experience(
            agent_id, simulation_id,
            observation="AAPL RSI at 34",
            action="BUY 100 shares at market",
            outcome="Price rose 5% in 3 days",
            keywords=["rsi", "aapl"],
            return_pct=0.05,
            market_regime="bullish",
            importance=0.8,
        )
        assert note.memory_type == "episodic"

        detail = await epi.get_experience_detail(note.id)
        assert detail is not None
        assert detail.observation == "AAPL RSI at 34"
        assert detail.return_pct == 0.05

    @pytest.mark.asyncio
    async def test_get_recent(self, db_session, simulation_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        epi = EpisodicMemory(db_session)

        for i in range(3):
            await epi.store_experience(
                agent_id, simulation_id,
                observation=f"Observation {i}",
                action=f"Action {i}",
                outcome=f"Outcome {i}",
            )

        recent = await epi.get_recent(agent_id, limit=2)
        assert len(recent) == 2

    @pytest.mark.asyncio
    async def test_add_reflection(self, db_session, simulation_id: uuid.UUID, agent_id: uuid.UUID) -> None:
        epi = EpisodicMemory(db_session)

        note = await epi.store_experience(
            agent_id, simulation_id,
            observation="Market crashed 3%",
            action="Panic sold all positions",
            outcome="Lost 5% of portfolio",
        )

        await epi.add_reflection(note.id, "Should have held — panic selling is suboptimal")
        detail = await epi.get_experience_detail(note.id)
        assert detail is not None
        assert "panic selling" in detail.reflection
