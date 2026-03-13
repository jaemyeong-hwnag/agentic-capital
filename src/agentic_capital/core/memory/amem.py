"""A-MEM Zettelkasten memory note — atomic, linked, searchable."""

from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class MemoryNote(BaseModel):
    """A-MEM Zettelkasten-style memory note.

    Each note is atomic, self-contained, and linked to related notes.
    Q-value determines retention priority (REMEMBERER decay).
    """

    id: UUID = Field(default_factory=uuid4)
    agent_id: UUID
    memory_type: str  # episodic, semantic, procedural

    # A-MEM fields
    context: str  # Situation description
    keywords: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    links: list[UUID] = Field(default_factory=list)  # Cross-references

    # REMEMBERER fields
    q_value: float = Field(default=0.5, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    access_count: int = 0

    # Embedding (stored separately in vector DB)
    embedding: list[float] | None = None


class EpisodicDetail(BaseModel):
    """Detailed record of a specific experience."""

    memory_id: UUID
    observation: str
    action: str
    outcome: str
    return_pct: float | None = None
    market_regime: str = ""
    reflection: str = ""
