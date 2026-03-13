"""Unit tests for LangSmith tracing setup."""

import os
from unittest.mock import patch

import pytest

from agentic_capital.infra.tracing import setup_tracing


class TestSetupTracing:
    def test_disabled_when_no_key(self):
        with patch("agentic_capital.infra.tracing.settings") as mock_settings:
            mock_settings.langchain_tracing_v2 = False
            mock_settings.langchain_api_key = ""
            result = setup_tracing()
            assert result is False

    def test_disabled_when_flag_false(self):
        with patch("agentic_capital.infra.tracing.settings") as mock_settings:
            mock_settings.langchain_tracing_v2 = False
            mock_settings.langchain_api_key = "test-key"
            result = setup_tracing()
            assert result is False

    def test_disabled_when_no_api_key(self):
        with patch("agentic_capital.infra.tracing.settings") as mock_settings:
            mock_settings.langchain_tracing_v2 = True
            mock_settings.langchain_api_key = ""
            result = setup_tracing()
            assert result is False

    def test_enabled_sets_env_vars(self):
        with patch("agentic_capital.infra.tracing.settings") as mock_settings:
            mock_settings.langchain_tracing_v2 = True
            mock_settings.langchain_api_key = "test-key-123"
            mock_settings.langchain_project = "test-project"
            result = setup_tracing()
            assert result is True
            assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
            assert os.environ.get("LANGCHAIN_API_KEY") == "test-key-123"
            assert os.environ.get("LANGCHAIN_PROJECT") == "test-project"

        # Cleanup
        os.environ.pop("LANGCHAIN_TRACING_V2", None)
        os.environ.pop("LANGCHAIN_API_KEY", None)
        os.environ.pop("LANGCHAIN_PROJECT", None)
