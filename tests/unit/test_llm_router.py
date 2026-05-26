"""Tests for LLM provider router."""

from unittest.mock import MagicMock, patch

import pytest

from agentic_capital.adapters.llm import router


def test_local_provider_names_enable_local_mode():
    with patch.object(router.settings, "llm_provider", "domain_llm_forge"):
        assert router.is_local_llm_enabled() is True


def test_router_builds_local_langchain_model():
    with patch.object(router.settings, "llm_provider", "local"), \
         patch.object(router.settings, "local_llm_base_url", "http://127.0.0.1:8080/v1"), \
         patch.object(router.settings, "local_llm_model", "finance_decision_model"), \
         patch.object(router.settings, "local_llm_api_key", ""), \
         patch.object(router.settings, "local_llm_timeout_seconds", 10.0), \
         patch.object(router.settings, "local_llm_temperature", 0.2):
        model = router.build_langchain_chat_model()

    assert model.model == "finance_decision_model"
    assert model.base_url == "http://127.0.0.1:8080/v1"


def test_router_uses_gemini_only_when_explicitly_configured():
    with patch.object(router.settings, "llm_provider", "gemini"), \
         patch("langchain_google_genai.ChatGoogleGenerativeAI", return_value=MagicMock()) as mock_cls:
        router.build_langchain_chat_model()

    mock_cls.assert_called_once()


def test_router_rejects_unknown_provider_instead_of_falling_back_to_gemini():
    with patch.object(router.settings, "llm_provider", "gemni"):
        with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
            router.build_langchain_chat_model()
