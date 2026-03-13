"""Tests for agent factory."""

from agentic_capital.core.agents.factory import create_agent_profile, create_random_personality


class TestAgentFactory:
    def test_random_personality_in_range(self) -> None:
        p = create_random_personality(seed=42)
        for val in p.to_list():
            assert 0.0 <= val <= 1.0

    def test_random_personality_reproducible(self) -> None:
        p1 = create_random_personality(seed=42)
        p2 = create_random_personality(seed=42)
        assert p1 == p2

    def test_random_personality_different_seeds(self) -> None:
        p1 = create_random_personality(seed=1)
        p2 = create_random_personality(seed=2)
        assert p1 != p2

    def test_create_agent_profile(self) -> None:
        profile = create_agent_profile(
            name="Analyst Alpha",
            philosophy="Technical analysis first",
            allocated_capital=50_000.0,
        )
        assert profile.name == "Analyst Alpha"
        assert profile.allocated_capital == 50_000.0
        assert profile.id is not None
