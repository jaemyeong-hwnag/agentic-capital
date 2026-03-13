"""Tests for A-MEM Zettelkasten memory notes."""

from uuid import uuid4

from agentic_capital.core.memory.amem import EpisodicDetail, MemoryNote


class TestMemoryNote:
    def test_create_note(self) -> None:
        agent_id = uuid4()
        note = MemoryNote(
            agent_id=agent_id,
            memory_type="episodic",
            context="RSI divergence on AAPL, volatile_bullish regime",
            keywords=["rsi_divergence", "aapl", "earnings_catalyst"],
            tags=["technical_signal", "high_conviction"],
            q_value=0.78,
        )
        assert note.agent_id == agent_id
        assert note.q_value == 0.78
        assert "rsi_divergence" in note.keywords

    def test_note_links(self) -> None:
        note1 = MemoryNote(agent_id=uuid4(), memory_type="episodic", context="First experience")
        note2 = MemoryNote(
            agent_id=note1.agent_id,
            memory_type="episodic",
            context="Related experience",
            links=[note1.id],
        )
        assert note1.id in note2.links

    def test_default_q_value(self) -> None:
        note = MemoryNote(agent_id=uuid4(), memory_type="semantic", context="Market knowledge")
        assert note.q_value == 0.5
        assert note.access_count == 0


class TestEpisodicDetail:
    def test_create_detail(self) -> None:
        detail = EpisodicDetail(
            memory_id=uuid4(),
            observation="AAPL RSI at 34, below oversold threshold",
            action="BUY 100 shares at market",
            outcome="Price rose 5% in 3 days",
            return_pct=0.05,
            market_regime="volatile_bullish",
            reflection="RSI divergence is a reliable signal in bullish regimes",
        )
        assert detail.return_pct == 0.05
        assert detail.market_regime == "volatile_bullish"
