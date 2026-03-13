"""Tests for application configuration."""

from agentic_capital.config import Settings


class TestConfig:
    def test_defaults(self) -> None:
        s = Settings()
        assert s.simulation_seed == 42
        assert s.initial_capital == 1_000_000
        assert s.log_level == "INFO"
        assert s.kis_is_paper is True

    def test_database_url_default(self) -> None:
        s = Settings()
        assert "agentic_capital" in s.database_url
        assert "asyncpg" in s.database_url
