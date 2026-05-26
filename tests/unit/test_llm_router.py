"""Tests for LLM provider router."""

from unittest.mock import MagicMock, patch

import pytest

from agentic_capital.adapters.llm import router
from agentic_capital.adapters.llm import local_finance_runtime
from agentic_capital import local_finance_smoke


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


def test_local_finance_health_accepts_expected_finance_model():
    response = MagicMock()
    response.json.return_value = {"ok": True, "model": "finance_decision_model", "llama_reachable": True}
    response.raise_for_status.return_value = None

    with patch.object(local_finance_runtime.settings, "local_llm_base_url", "http://127.0.0.1:8080/v1"), \
         patch.object(local_finance_runtime.settings, "local_llm_model", "finance_decision_model"), \
         patch.object(local_finance_runtime.settings, "local_llm_expected_health_model", ""), \
         patch("agentic_capital.adapters.llm.local_finance_runtime.httpx.get", return_value=response) as mock_get:
        result = local_finance_runtime.check_local_finance_health()

    assert result["actual_model"] == "finance_decision_model"
    mock_get.assert_called_once_with("http://127.0.0.1:8080/healthz", timeout=5.0)


def test_local_finance_health_rejects_psychology_model_for_finance():
    response = MagicMock()
    response.json.return_value = {"ok": True, "model": "psychology_profile_model", "llama_reachable": True}
    response.raise_for_status.return_value = None

    with patch.object(local_finance_runtime.settings, "local_llm_base_url", "http://127.0.0.1:18501/v1"), \
         patch.object(local_finance_runtime.settings, "local_llm_model", "finance_decision_model"), \
         patch.object(local_finance_runtime.settings, "local_llm_expected_health_model", ""), \
         patch("agentic_capital.adapters.llm.local_finance_runtime.httpx.get", return_value=response):
        with pytest.raises(local_finance_runtime.LocalFinanceRuntimeError, match="model_category_mismatch"):
            local_finance_runtime.check_local_finance_health()


def test_finance_smoke_passes_safe_no_context_action():
    response = MagicMock()
    response.json.return_value = {
        "choices": [{"message": {"content": '{"action":"CALL_TOOL","required_tools":["get_balance"]}'}}],
    }
    response.raise_for_status.return_value = None

    with patch.object(local_finance_runtime.settings, "local_llm_base_url", "http://127.0.0.1:8080/v1"), \
         patch.object(local_finance_runtime.settings, "local_llm_model", "finance_decision_model"), \
         patch.object(local_finance_runtime.settings, "local_llm_api_key", ""), \
         patch("agentic_capital.adapters.llm.local_finance_runtime.httpx.post", return_value=response):
        result = local_finance_runtime.run_local_finance_smoke()

    assert result["action"] == "CALL_TOOL"


def test_finance_smoke_rejects_buy_without_evidence_and_tools():
    with pytest.raises(local_finance_runtime.LocalFinanceRuntimeError, match="unsafe_trade_action"):
        local_finance_runtime.validate_finance_decision_payload({
            "action": "BUY",
            "symbol": "005930",
            "evidence_ids": [],
            "required_tools": [],
        })


def test_finance_smoke_cli_returns_zero_on_success(capsys):
    with patch("agentic_capital.local_finance_smoke.validate_local_finance_runtime", return_value={"ok": True}):
        result = local_finance_smoke.main()

    assert result == 0
    assert '"ok": true' in capsys.readouterr().out


def test_finance_smoke_cli_returns_one_on_runtime_error(capsys):
    with patch(
        "agentic_capital.local_finance_smoke.validate_local_finance_runtime",
        side_effect=local_finance_runtime.LocalFinanceRuntimeError("local_llm_model_mismatch"),
    ):
        result = local_finance_smoke.main()

    assert result == 1
    output = capsys.readouterr().out
    assert '"ok": false' in output
    assert "local_llm_model_mismatch" in output
