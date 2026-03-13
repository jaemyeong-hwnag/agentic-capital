"""Episodic memory — specific experiences stored in PostgreSQL.

Phase 1: JSONB embeddings with application-level cosine similarity.
Phase 2: Migrate to pgvector VECTOR column + HNSW index.

Stores concrete experiences (observation → action → outcome)
with embeddings for similarity search and REMEMBERER Q-value decay.
"""

from __future__ import annotations

import math
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentic_capital.core.memory.amem import AMEMStore, EpisodicDetail, MemoryNote
from agentic_capital.infra.models.memory import EpisodicDetailModel, MemoryModel


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class EpisodicMemory:
    """Experience-based memory with similarity search."""

    MEMORY_TYPE = "episodic"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._store = AMEMStore(session)

    async def store_experience(
        self,
        agent_id: uuid.UUID,
        simulation_id: uuid.UUID,
        observation: str,
        action: str,
        outcome: str,
        *,
        context_summary: str = "",
        keywords: list[str] | None = None,
        tags: list[str] | None = None,
        return_pct: float | None = None,
        market_regime: str = "",
        embedding: list[float] | None = None,
        importance: float = 0.5,
    ) -> MemoryNote:
        """Store a complete experience (observation → action → outcome)."""
        note = MemoryNote(
            agent_id=agent_id,
            simulation_id=simulation_id,
            memory_type=self.MEMORY_TYPE,
            context=context_summary or f"{observation} → {action} → {outcome}",
            keywords=keywords or [],
            tags=tags or [],
            importance=importance,
            q_value=max(0.5, importance),
            embedding=embedding,
        )
        created_note = await self._store.create(note)

        detail = EpisodicDetail(
            memory_id=created_note.id,
            observation=observation,
            action=action,
            outcome=outcome,
            return_pct=return_pct,
            market_regime=market_regime,
        )
        await self._store.create_episodic(detail)

        return created_note

    async def search_similar(
        self,
        agent_id: uuid.UUID,
        query_embedding: list[float],
        *,
        limit: int = 5,
        min_similarity: float = 0.3,
    ) -> list[tuple[MemoryNote, float]]:
        """Search for similar experiences by embedding cosine similarity.

        Phase 1: Application-level similarity on JSONB embeddings.
        Phase 2: pgvector HNSW index for sub-ms queries.

        Returns list of (note, similarity_score) sorted by score descending.
        """
        stmt = (
            select(MemoryModel)
            .where(
                MemoryModel.agent_id == agent_id,
                MemoryModel.memory_type == self.MEMORY_TYPE,
                MemoryModel.embedding.isnot(None),
                MemoryModel.decayed_at.is_(None),
            )
            .order_by(MemoryModel.q_value.desc())
            .limit(200)  # Pre-filter by q_value, then re-rank by similarity
        )
        result = await self._session.execute(stmt)

        scored: list[tuple[MemoryNote, float]] = []
        for model in result.scalars():
            sim = _cosine_similarity(query_embedding, model.embedding or [])
            if sim >= min_similarity:
                scored.append((AMEMStore._to_note(model), sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    async def get_experience_detail(self, memory_id: uuid.UUID) -> EpisodicDetail | None:
        """Get the detailed experience record for a memory note."""
        result = await self._session.execute(
            select(EpisodicDetailModel).where(EpisodicDetailModel.memory_id == memory_id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            return None

        return EpisodicDetail(
            memory_id=model.memory_id,
            observation=model.observation,
            action=model.action,
            outcome=model.outcome,
            return_pct=model.return_pct,
            market_regime=model.market_regime,
            reflection=model.reflection,
        )

    async def add_reflection(self, memory_id: uuid.UUID, reflection: str) -> None:
        """Add a reflection to an existing experience."""
        result = await self._session.execute(
            select(EpisodicDetailModel).where(EpisodicDetailModel.memory_id == memory_id)
        )
        model = result.scalar_one_or_none()
        if model is not None:
            model.reflection = reflection
            await self._session.flush()

    async def get_recent(
        self,
        agent_id: uuid.UUID,
        *,
        limit: int = 10,
    ) -> list[MemoryNote]:
        """Get most recent episodic memories."""
        stmt = (
            select(MemoryModel)
            .where(
                MemoryModel.agent_id == agent_id,
                MemoryModel.memory_type == self.MEMORY_TYPE,
                MemoryModel.decayed_at.is_(None),
            )
            .order_by(MemoryModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [AMEMStore._to_note(m) for m in result.scalars()]
