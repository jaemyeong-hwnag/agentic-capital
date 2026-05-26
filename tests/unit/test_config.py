"""Tests for application configuration."""

import os
from unittest.mock import patch

from agentic_capital.config import Settings


class TestConfig:
    def test_defaults(self) -> None:
        s = Settings(_env_file=None)
        assert s.simulation_seed == 42
        assert s.initial_capital == 1_000_000
        assert s.log_level == "INFO"
        assert s.kis_is_paper is True
        assert s.llm_provider == "local"
        assert s.local_llm_model == "finance_decision_model"
        assert s.local_embedding_model == "finance_embedding_model"

    def test_database_url_default(self) -> None:
        s = Settings(_env_file=None)
        assert "agentic_capital" in s.database_url
        assert "asyncpg" in s.database_url

    def test_local_llm_provider_alias(self) -> None:
        with patch.dict(os.environ, {"LOCAL_LLM_PROVIDER": "local"}, clear=False):
            s = Settings(_env_file=None)
        assert s.llm_provider == "local"
