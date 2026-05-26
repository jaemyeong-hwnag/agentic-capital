"""Tests for the local psychology sidecar runtime guards."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentic_capital import local_psychology_smoke
from agentic_capital.adapters.llm import local_psychology_runtime


def test_local_psychology_health_accepts_expected_model() -> None:
    response = MagicMock()
    response.json.return_value = {"ok": True, "model": "psychology_model_suite", "llama_reachable": True}
    response.raise_for_status.return_value = None

    with patch.object(local_psychology_runtime.settings, "local_psychology_base_url", "http://127.0.0.1:19400/v1"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_model", "psychology_model_suite"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_expected_health_model", ""), \
         patch("agentic_capital.adapters.llm.local_psychology_runtime.httpx.get", return_value=response) as mock_get:
        result = local_psychology_runtime.check_local_psychology_health()

    assert result["actual_model"] == "psychology_model_suite"
    mock_get.assert_called_once_with("http://127.0.0.1:19400/healthz", timeout=5.0)


def test_local_psychology_health_rejects_finance_model() -> None:
    response = MagicMock()
    response.json.return_value = {"ok": True, "model": "finance_decision_model", "llama_reachable": True}
    response.raise_for_status.return_value = None

    with patch.object(local_psychology_runtime.settings, "local_psychology_base_url", "http://127.0.0.1:19400/v1"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_model", "psychology_model_suite"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_expected_health_model", ""), \
         patch("agentic_capital.adapters.llm.local_psychology_runtime.httpx.get", return_value=response), \
         pytest.raises(local_psychology_runtime.LocalPsychologyRuntimeError, match="model_category_mismatch"):
        local_psychology_runtime.check_local_psychology_health()


def test_psychology_payload_accepts_context_only_schema() -> None:
    result = local_psychology_runtime.validate_psychology_context_payload({
        "signals": [],
        "agent_state_patch": {"risk_tags": ["revenge_trading_risk"]},
        "evidence_ids": ["memory-1"],
        "confidence": 0.72,
        "uncertainty": ["quote and balance are finance-only inputs"],
        "risk_tags": ["overconfidence_risk"],
        "allowed_downstream_use": "context_only",
    })

    assert result["evidence_count"] == 1
    assert result["allowed_downstream_use"] == "context_only"


@pytest.mark.parametrize(
    "payload,error",
    [
        ({"action": "BUY", "evidence_ids": [], "confidence": 0.5, "uncertainty": []}, "trade_action_leak"),
        (
            {
                "evidence_ids": [],
                "confidence": 0.5,
                "uncertainty": [],
                "allowed_downstream_use": "trade_decision",
            },
            "disallowed_downstream_use",
        ),
        ({"evidence_ids": [], "confidence": 1.7, "uncertainty": []}, "confidence_out_of_bounds"),
        ({"evidence_ids": [], "confidence": 0.4, "uncertainty": ["진단 필요"]}, "clinical_claim"),
    ],
)
def test_psychology_payload_rejects_runtime_boundary_violations(payload, error) -> None:
    with pytest.raises(local_psychology_runtime.LocalPsychologyRuntimeError, match=error):
        local_psychology_runtime.validate_psychology_context_payload(payload)


def test_psychology_smoke_passes_safe_context_payload() -> None:
    response = MagicMock()
    response.json.return_value = {
        "choices": [{
            "message": {
                "content": (
                    '{"evidence_ids":["runtime_schema_contract"],"confidence":0.61,'
                    '"uncertainty":["requires finance risk guard before any trade"],'
                    '"risk_tags":["revenge_trading_risk"],"agent_state_patch":{},'
                    '"allowed_downstream_use":"context_only"}'
                ),
            },
        }],
    }
    response.raise_for_status.return_value = None

    with patch.object(local_psychology_runtime.settings, "local_psychology_base_url", "http://127.0.0.1:19400/v1"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_model", "psychology_model_suite"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_api_key", ""), \
         patch("agentic_capital.adapters.llm.local_psychology_runtime.httpx.post", return_value=response) as mock_post:
        result = local_psychology_runtime.run_local_psychology_smoke()

    assert result["ok"] is True
    assert result["evidence_count"] == 1
    request_payload = mock_post.call_args.kwargs["json"]
    assert request_payload["model"] == "psychology_model_suite"
    assert "Do not output BUY, SELL" in request_payload["messages"][0]["content"]


def test_psychology_smoke_repairs_invalid_json_to_context_only() -> None:
    response = MagicMock()
    response.json.return_value = {
        "choices": [{"message": {"content": '{"evidence_ids":[],"risk_tags":[broken-token]}'}}],
        "rag": {
            "retrieved": [
                {"doc_id": "runtime_schema_contract.md"},
                {"doc_id": "agentic_capital_integration_reference.md"},
            ],
        },
    }
    response.raise_for_status.return_value = None

    with patch.object(local_psychology_runtime.settings, "local_psychology_base_url", "http://127.0.0.1:19400/v1"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_model", "psychology_model_suite"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_api_key", ""), \
         patch("agentic_capital.adapters.llm.local_psychology_runtime.httpx.post", return_value=response):
        result = local_psychology_runtime.run_local_psychology_smoke()

    assert result["ok"] is True
    assert result["confidence"] == 0.0
    assert result["evidence_count"] == 2
    assert result["repair_applied"] == "invalid_json_to_context_only"


def test_psychology_runtime_skips_when_not_required() -> None:
    with patch.object(local_psychology_runtime.settings, "local_psychology_readiness_required", False):
        result = local_psychology_runtime.validate_local_psychology_runtime()

    assert result == {"ok": True, "skipped": "local_psychology_readiness_required_false"}


def test_psychology_smoke_cli_returns_zero_on_success(capsys) -> None:
    with patch("agentic_capital.local_psychology_smoke.validate_local_psychology_runtime", return_value={"ok": True}):
        result = local_psychology_smoke.main()

    assert result == 0
    assert '"ok": true' in capsys.readouterr().out


def test_psychology_smoke_cli_returns_one_on_runtime_error(capsys) -> None:
    with patch(
        "agentic_capital.local_psychology_smoke.validate_local_psychology_runtime",
        side_effect=local_psychology_runtime.LocalPsychologyRuntimeError("local_psychology_model_mismatch"),
    ):
        result = local_psychology_smoke.main()

    assert result == 1
    output = capsys.readouterr().out
    assert '"ok": false' in output
    assert "local_psychology_model_mismatch" in output
