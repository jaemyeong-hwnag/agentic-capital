"""A-MEM Zettelkasten memory — atomic, linked, searchable notes.

Implements CRUD operations for A-MEM notes backed by PostgreSQL.
Each note has keywords, tags, cross-references, and a Q-value for
REMEMBERER-style retention decay.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_capital.infra.models.memory import EpisodicDetailModel, MemoryModel


class MemoryNote(BaseModel):
    """A-MEM Zettelkasten-style memory note."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    agent_id: uuid.UUID
    simulation_id: uuid.UUID
    memory_type: str  # episodic, semantic, procedural

    # A-MEM fields
    context: str
    keywords: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    links: list[uuid.UUID] = Field(default_factory=list)

    # REMEMBERER fields
    q_value: float = Field(default=0.5, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    access_count: int = 0

    embedding: list[float] | None = None


class EpisodicDetail(BaseModel):
    """Detailed record of a specific experience."""

    memory_id: uuid.UUID
    observation: str
    action: str
    outcome: str
    return_pct: float | None = None
    market_regime: str = ""
    reflection: str = ""


class AMEMStore:
    """A-MEM note CRUD backed by PostgreSQL."""

    DECAY_RATE = 0.05

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, note: MemoryNote) -> MemoryNote:
        """Create a new memory note."""
        model = MemoryModel(
            id=note.id,
            agent_id=note.agent_id,
            simulation_id=note.simulation_id,
            memory_type=note.memory_type,
            context=note.context,
            keywords=note.keywords,
            tags=note.tags,
            links=[str(lid) for lid in note.links],
            q_value=note.q_value,
            importance=note.importance,
            access_count=note.access_count,
            embedding=note.embedding,
        )
        self._session.add(model)
        await self._session.flush()
        return note

    async def get(self, memory_id: uuid.UUID) -> MemoryNote | None:
        """Get a note by ID, incrementing access_count."""
        result = await self._session.execute(
            select(MemoryModel).where(MemoryModel.id == memory_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None

        # Increment access
        model.access_count += 1
        model.last_accessed = datetime.now()
        await self._session.flush()

        return self._to_note(model)

    async def search_by_keywords(
        self,
        agent_id: uuid.UUID,
        keywords: list[str],
        *,
        limit: int = 10,
    ) -> list[MemoryNote]:
        """Search notes by keyword overlap (JSONB contains)."""
        stmt = (
            select(MemoryModel)
            .where(
                MemoryModel.agent_id == agent_id,
                MemoryModel.decayed_at.is_(None),
            )
            .order_by(MemoryModel.q_value.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        notes = []
        for model in result.scalars():
            stored_kw = set(model.keywords or [])
            if stored_kw & set(keywords):
                notes.append(self._to_note(model))
        return notes

    async def search_by_tags(
        self,
        agent_id: uuid.UUID,
        tags: list[str],
        *,
        limit: int = 10,
    ) -> list[MemoryNote]:
        """Search notes by tag overlap."""
        stmt = (
            select(MemoryModel)
            .where(
                MemoryModel.agent_id == agent_id,
                MemoryModel.decayed_at.is_(None),
            )
            .order_by(MemoryModel.q_value.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        notes = []
        for model in result.scalars():
            stored_tags = set(model.tags or [])
            if stored_tags & set(tags):
                notes.append(self._to_note(model))
        return notes

    async def get_linked(self, memory_id: uuid.UUID) -> list[MemoryNote]:
        """Get all notes linked from a given note."""
        note = await self.get(memory_id)
        if note is None or not note.links:
            return []

        link_strs = [str(lid) for lid in note.links]
        stmt = select(MemoryModel).where(MemoryModel.id.in_(link_strs))
        result = await self._session.execute(stmt)
        return [self._to_note(m) for m in result.scalars()]

    async def add_link(self, from_id: uuid.UUID, to_id: uuid.UUID) -> None:
        """Add a cross-reference link between two notes."""
        result = await self._session.execute(
            select(MemoryModel).where(MemoryModel.id == from_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return

        links = list(model.links or [])
        to_str = str(to_id)
        if to_str not in links:
            links.append(to_str)
            model.links = links
            await self._session.flush()

    async def update_q_value(self, memory_id: uuid.UUID, delta: float) -> float:
        """Update Q-value (reinforcement). Returns new value."""
        result = await self._session.execute(
            select(MemoryModel).where(MemoryModel.id == memory_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return 0.0

        new_q = max(0.0, min(1.0, model.q_value + delta))
        model.q_value = new_q
        await self._session.flush()
        return new_q

    async def decay(self, agent_id: uuid.UUID, *, threshold: float = 0.05) -> int:
        """Apply REMEMBERER decay to all notes. Returns count of decayed notes."""
        stmt = (
            select(MemoryModel)
            .where(
                MemoryModel.agent_id == agent_id,
                MemoryModel.decayed_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        decayed_count = 0

        for model in result.scalars():
            model.q_value = max(0.0, model.q_value - self.DECAY_RATE)
            if model.q_value <= threshold:
                model.decayed_at = datetime.now()
                decayed_count += 1

        await self._session.flush()
        return decayed_count

    async def create_episodic(self, detail: EpisodicDetail) -> EpisodicDetail:
        """Create an episodic detail linked to a memory note."""
        model = EpisodicDetailModel(
            id=uuid.uuid4(),
            memory_id=detail.memory_id,
            observation=detail.observation,
            action=detail.action,
            outcome=detail.outcome,
            return_pct=detail.return_pct,
            market_regime=detail.market_regime,
            reflection=detail.reflection,
        )
        self._session.add(model)
        await self._session.flush()
        return detail

    async def list_by_agent(
        self,
        agent_id: uuid.UUID,
        *,
        memory_type: str | None = None,
        active_only: bool = True,
        limit: int = 50,
    ) -> list[MemoryNote]:
        """List notes for an agent, optionally filtered by type."""
        stmt = select(MemoryModel).where(MemoryModel.agent_id == agent_id)

        if memory_type:
            stmt = stmt.where(MemoryModel.memory_type == memory_type)
        if active_only:
            stmt = stmt.where(MemoryModel.decayed_at.is_(None))

        stmt = stmt.order_by(MemoryModel.q_value.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_note(m) for m in result.scalars()]

    @staticmethod
    def _to_note(model: MemoryModel) -> MemoryNote:
        return MemoryNote(
            id=model.id,
            agent_id=model.agent_id,
            simulation_id=model.simulation_id,
            memory_type=model.memory_type,
            context=model.context,
            keywords=model.keywords or [],
            tags=model.tags or [],
            links=[uuid.UUID(lid) for lid in (model.links or [])],
            q_value=model.q_value,
            importance=model.importance,
            access_count=model.access_count,
            embedding=model.embedding,
        )
