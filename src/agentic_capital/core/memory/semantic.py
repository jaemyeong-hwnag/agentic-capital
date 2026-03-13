"""Semantic memory — accumulated knowledge in PostgreSQL.

Stores long-term knowledge (market patterns, investment principles)
as A-MEM notes with memory_type='semantic'.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_capital.core.memory.amem import AMEMStore, MemoryNote
from agentic_capital.infra.models.memory import MemoryModel

logger = structlog.get_logger()


class SemanticMemory:
    """Long-term knowledge store backed by PostgreSQL memories table."""

    MEMORY_TYPE = "semantic"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._store = AMEMStore(session)

    async def store_knowledge(
        self,
        agent_id: uuid.UUID,
        simulation_id: uuid.UUID,
        context: str,
        *,
        keywords: list[str] | None = None,
        tags: list[str] | None = None,
        importance: float = 0.5,
    ) -> MemoryNote:
        """Store a piece of accumulated knowledge."""
        note = MemoryNote(
            agent_id=agent_id,
            simulation_id=simulation_id,
            memory_type=self.MEMORY_TYPE,
            context=context,
            keywords=keywords or [],
            tags=tags or [],
            importance=importance,
            q_value=max(0.5, importance),
        )
        try:
            created = await self._store.create(note)
            logger.debug("semantic_stored", agent_id=str(agent_id), note_id=str(created.id))
            return created
        except Exception:
            logger.exception("semantic_store_failed", agent_id=str(agent_id))
            raise

    async def search(
        self,
        agent_id: uuid.UUID,
        *,
        keywords: list[str] | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> list[MemoryNote]:
        """Search semantic knowledge by keywords or tags."""
        if keywords:
            return await self._store.search_by_keywords(agent_id, keywords, limit=limit)
        if tags:
            return await self._store.search_by_tags(agent_id, tags, limit=limit)
        return await self._store.list_by_agent(
            agent_id, memory_type=self.MEMORY_TYPE, limit=limit
        )

    async def update_from_reflection(
        self,
        memory_id: uuid.UUID,
        new_context: str,
        *,
        q_delta: float = 0.1,
    ) -> MemoryNote | None:
        """Update knowledge based on Reflection."""
        try:
            result = await self._session.execute(
                select(MemoryModel).where(MemoryModel.id == memory_id)
            )
            model = result.scalar_one_or_none()
            if model is None:
                return None

            model.context = new_context
            await self._store.update_q_value(memory_id, q_delta)
            await self._session.flush()
            logger.debug("semantic_reflection_updated", memory_id=str(memory_id))
            return await self._store.get(memory_id)
        except Exception:
            logger.exception("semantic_reflection_failed", memory_id=str(memory_id))
            raise

    async def get_top_knowledge(
        self,
        agent_id: uuid.UUID,
        *,
        limit: int = 5,
    ) -> list[MemoryNote]:
        """Get highest Q-value semantic memories for prompt injection."""
        return await self._store.list_by_agent(
            agent_id, memory_type=self.MEMORY_TYPE, limit=limit
        )

    async def count(self, agent_id: uuid.UUID) -> int:
        """Count active semantic memories for an agent."""
        try:
            result = await self._session.execute(
                select(func.count())
                .select_from(MemoryModel)
                .where(
                    MemoryModel.agent_id == agent_id,
                    MemoryModel.memory_type == self.MEMORY_TYPE,
                    MemoryModel.decayed_at.is_(None),
                )
            )
            return result.scalar_one()
        except Exception:
            logger.exception("semantic_count_failed", agent_id=str(agent_id))
            return 0
