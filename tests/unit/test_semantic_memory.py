"""Tests for Semantic Memory — validates MemoryNote creation for semantic type."""

from uuid import uuid4

from agentic_capital.core.memory.amem import MemoryNote


class TestSemanticMemoryNote:
    def test_create_semantic_note(self) -> None:
        note = MemoryNote(
            agent_id=uuid4(),
            simulation_id=uuid4(),
            memory_type="semantic",
            context="Tech sector tends to rally after Fed rate pauses",
            keywords=["fed", "rate_pause", "tech_rally"],
            tags=["macro", "sector_rotation"],
            importance=0.8,
            q_value=0.8,
        )
        assert note.memory_type == "semantic"
        assert note.importance == 0.8
        assert "fed" in note.keywords

    def test_semantic_note_defaults(self) -> None:
        note = MemoryNote(
            agent_id=uuid4(),
            simulation_id=uuid4(),
            memory_type="semantic",
            context="Diversification reduces portfolio variance",
        )
        assert note.q_value == 0.5
        assert note.keywords == []
        assert note.tags == []
        assert note.links == []
