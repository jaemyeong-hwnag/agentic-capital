"""Tests for the local psychology sidecar runtime guards."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentic_capital import local_psychology_smoke
from agentic_capital.adapters.llm import local_finance_runtime, local_psychology_runtime


class _AsyncClientStub:
    def __init__(self, response):
        self.response = response
        self.post_kwargs = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, **kwargs):
        self.post_url = url
        self.post_kwargs = kwargs
        return self.response


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


def test_local_psychology_health_accepts_direct_llama_server_model_alias() -> None:
    gateway_missing = MagicMock()
    gateway_missing.raise_for_status.side_effect = RuntimeError("404")
    health = MagicMock()
    health.json.return_value = {"status": "ok"}
    health.raise_for_status.return_value = None
    models = MagicMock()
    models.json.return_value = {"data": [{"id": "psychology_model_suite"}]}
    models.raise_for_status.return_value = None

    with patch.object(local_psychology_runtime.settings, "local_psychology_base_url", "http://127.0.0.1:18080/v1"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_model", "psychology_model_suite"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_expected_health_model", ""), \
         patch(
             "agentic_capital.adapters.llm.local_psychology_runtime.httpx.get",
             side_effect=[gateway_missing, health, models],
         ) as mock_get:
        result = local_psychology_runtime.check_local_psychology_health()

    assert result["actual_model"] == "psychology_model_suite"
    assert result["health_url"] == "http://127.0.0.1:18080/health"
    assert mock_get.call_args_list[0].args[0] == "http://127.0.0.1:18080/healthz"
    assert mock_get.call_args_list[1].args[0] == "http://127.0.0.1:18080/health"
    assert mock_get.call_args_list[2].args[0] == "http://127.0.0.1:18080/v1/models"


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
    assert result["schema_status"] == "validated"


def test_psychology_payload_rejects_order_mutation_fields() -> None:
    with pytest.raises(local_psychology_runtime.LocalPsychologyRuntimeError, match="order_mutation_key"):
        local_psychology_runtime.validate_psychology_context_payload({
            "signals": [],
            "agent_state_patch": {"order_permission": True},
            "evidence_ids": ["memory-1"],
            "confidence": 0.72,
            "uncertainty": ["psychology context cannot mutate order authority"],
            "risk_tags": ["impulsivity_risk"],
            "allowed_downstream_use": "context_only",
        })


def test_build_finance_soft_context_strips_non_soft_psychology_fields() -> None:
    result = local_psychology_runtime.build_finance_soft_context({
        "signals": [{"name": "overconfidence"}],
        "agent_state_patch": {"attention": "risk_review"},
        "evidence_ids": ["memory-1"],
        "confidence": 0.72,
        "uncertainty": ["needs finance tools before any trade"],
        "risk_tags": ["overconfidence_risk"],
        "allowed_downstream_use": "risk_context_not_alpha",
    })

    assert result["use_as"] == "soft_risk_context_not_alpha"
    assert result["schema_status"] == "validated"
    assert "trade_action" in result["forbidden_use"]
    assert "risk_limit_override" in result["forbidden_use"]
    assert "signals" not in result
    assert "action" not in result


def test_finance_decision_rejects_unsafe_psychology_context() -> None:
    with pytest.raises(local_finance_runtime.LocalFinanceRuntimeError, match="psychology_context_unsafe"):
        local_finance_runtime.validate_finance_decision_payload({
            "action": "HOLD",
            "evidence_ids": [],
            "required_tools": [],
            "psychology_context": {
                "action": "BUY",
                "evidence_ids": ["memory-1"],
                "confidence": 0.7,
                "uncertainty": ["unsafe action leak"],
                "allowed_downstream_use": "context_only",
            },
        })


@pytest.mark.asyncio
async def test_run_local_psychology_context_returns_soft_context_only() -> None:
    response = MagicMock()
    response.status_code = 200
    response.text = '{"ok":true}'
    response.json.return_value = {
        "choices": [{
            "message": {
                "content": (
                    '{"signals":[{"name":"overconfidence"}],'
                    '"agent_state_patch":{"attention":"risk_review"},'
                    '"evidence_ids":["memory-1"],"confidence":0.72,'
                    '"uncertainty":["requires finance tools before any trade"],'
                    '"risk_tags":["overconfidence_risk"],'
                    '"allowed_downstream_use":"context_only"}'
                ),
            },
        }],
    }
    response.raise_for_status.return_value = None
    client = _AsyncClientStub(response)

    with patch.object(local_psychology_runtime.settings, "local_psychology_base_url", "http://127.0.0.1:19400/v1"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_model", "psychology_model_suite"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_api_key", ""), \
         patch("agentic_capital.adapters.llm.local_psychology_runtime.httpx.AsyncClient", return_value=client):
        result = await local_psychology_runtime.run_local_psychology_context(
            request_id="cycle-1",
            agent_context={"agent_id": "CEO-Alpha", "live_order_enabled": False},
            input_text="recent cycle trace",
        )

    assert result["ok"] is True
    assert result["status_code"] == 200
    assert result["context"]["allowed_downstream_use"] == "context_only"
    assert result["soft_context"]["use_as"] == "soft_risk_context_not_alpha"
    assert result["soft_context"]["schema_status"] == "validated"
    assert "signals" not in result["soft_context"]
    assert "trade_action" in result["soft_context"]["forbidden_use"]
    assert "risk_limit_override" in result["soft_context"]["forbidden_use"]
    assert client.post_url == "http://127.0.0.1:19400/v1/chat/completions"
    request_payload = client.post_kwargs["json"]
    assert request_payload["model"] == "psychology_model_suite"
    assert "Never output BUY, SELL" in request_payload["messages"][0]["content"]


@pytest.mark.asyncio
async def test_run_local_psychology_context_completes_partial_json_schema() -> None:
    response = MagicMock()
    response.status_code = 200
    response.text = '{"ok":true}'
    response.json.return_value = {
        "choices": [{
            "message": {
                "content": (
                    '{"confidence":0.42,"risk_tags":"overconfidence_risk",'
                    '"allowed_downstream_use":"risk_context_not_alpha"}'
                ),
            },
        }],
        "rag": {"retrieved": [{"doc_id": "cycle-trace-1"}]},
    }
    response.raise_for_status.return_value = None
    client = _AsyncClientStub(response)

    with patch.object(local_psychology_runtime.settings, "local_psychology_base_url", "http://127.0.0.1:19400/v1"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_model", "psychology_model_suite"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_api_key", ""), \
         patch("agentic_capital.adapters.llm.local_psychology_runtime.httpx.AsyncClient", return_value=client):
        result = await local_psychology_runtime.run_local_psychology_context(
            request_id="cycle-1",
            agent_context={"agent_id": "CEO-Alpha"},
            input_text="recent cycle trace",
        )

    assert result["ok"] is True
    assert result["context"]["schema_status"] == "schema_completed"
    assert result["context"]["evidence_ids"] == ["cycle-trace-1"]
    assert result["context"]["allowed_downstream_use"] == "context_only"
    assert "overconfidence_risk" in result["context"]["risk_tags"]
    assert "schema_completed" in result["context"]["risk_tags"]
    assert result["soft_context"]["schema_status"] == "schema_completed"
    assert result["soft_context"]["use_as"] == "soft_risk_context_not_alpha"
    assert "risk_limit_override" in result["soft_context"]["forbidden_use"]


@pytest.mark.asyncio
async def test_run_local_psychology_context_repairs_boundary_violation_to_context_only() -> None:
    response = MagicMock()
    response.status_code = 200
    response.text = '{"ok":true}'
    response.json.return_value = {
        "choices": [{
            "message": {
                "content": (
                    '{"evidence_ids":["runtime_schema_contract.md"],"confidence":0.2,'
                    '"uncertainty":["model attempted an order authority field"],'
                    '"risk_tags":["boundary_violation"],'
                    '"agent_state_patch":{"order_permission":true},'
                    '"allowed_downstream_use":"context_only"}'
                ),
            },
        }],
    }
    response.raise_for_status.return_value = None
    client = _AsyncClientStub(response)

    with patch.object(local_psychology_runtime.settings, "local_psychology_base_url", "http://127.0.0.1:19400/v1"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_model", "psychology_model_suite"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_api_key", ""), \
         patch("agentic_capital.adapters.llm.local_psychology_runtime.httpx.AsyncClient", return_value=client):
        result = await local_psychology_runtime.run_local_psychology_context(
            request_id="cycle-1",
            agent_context={"agent": "Analyst-Beta"},
            input_text="pre-cycle observation",
        )

    assert result["ok"] is True
    assert result["repair_applied"] == "validation_failure_to_context_only"
    assert result["context"]["agent_state_patch"] == {}
    assert result["context"]["schema_status"] == "schema_repaired_context_only"
    assert "psychology_validation_repaired" in result["context"]["risk_tags"]
    assert "order_permission" not in result["soft_context"]


@pytest.mark.asyncio
async def test_run_local_psychology_context_repairs_unsafe_raw_preview_to_hash_only() -> None:
    response = MagicMock()
    response.status_code = 200
    response.text = '{"ok":true}'
    response.json.return_value = {
        "choices": [{
            "message": {
                "content": (
                    '{"signals":["local runtime diagnosis","execute order boundary"],'
                    '"agent_state_patch":{},'
                    '"evidence_ids":["runtime_schema_contract.md"],"confidence":0.0,'
                    '"uncertainty":["contextual_dependency_under_reviewed"],'
                    '"risk_tags":["pre_cycle_context"],'
                    '"allowed_downstream_use":"context_only"}'
                ),
            },
        }],
    }
    response.raise_for_status.return_value = None
    client = _AsyncClientStub(response)

    with patch.object(local_psychology_runtime.settings, "local_psychology_base_url", "http://127.0.0.1:19400/v1"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_model", "psychology_model_suite"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_api_key", ""), \
         patch("agentic_capital.adapters.llm.local_psychology_runtime.httpx.AsyncClient", return_value=client):
        result = await local_psychology_runtime.run_local_psychology_context(
            request_id="cycle-1",
            agent_context={"agent": "CEO-Alpha"},
            input_text="pre-cycle observation",
        )

    assert result["ok"] is True
    assert result["repair_applied"] == "validation_failure_to_context_only"
    assert result["context"]["schema_status"] == "schema_repaired_context_only"
    assert any(item.startswith("raw_output_sha256:") for item in result["context"]["uncertainty"])
    assert "diagnosis" not in " ".join(result["context"]["uncertainty"]).lower()
    assert "execute order" not in " ".join(result["context"]["uncertainty"]).lower()


@pytest.mark.asyncio
async def test_run_local_psychology_context_sends_compact_input_text() -> None:
    response = MagicMock()
    response.status_code = 200
    response.text = '{"ok":true}'
    response.json.return_value = {
        "choices": [{
            "message": {
                "content": (
                    '{"evidence_ids":["cycle"],"confidence":0.1,"uncertainty":[],'
                    '"risk_tags":[],"allowed_downstream_use":"context_only"}'
                ),
            },
        }],
    }
    response.raise_for_status.return_value = None
    client = _AsyncClientStub(response)

    with patch.object(local_psychology_runtime.settings, "local_psychology_base_url", "http://127.0.0.1:19400/v1"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_model", "psychology_model_suite"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_api_key", ""), \
         patch("agentic_capital.adapters.llm.local_psychology_runtime.httpx.AsyncClient", return_value=client):
        await local_psychology_runtime.run_local_psychology_context(
            request_id="cycle-1",
            agent_context={"agent_id": "CEO-Alpha"},
            input_text="token " * 1000,
        )

    content = client.post_kwargs["json"]["messages"][1]["content"]
    assert len(content) < 1300
    assert "token " * 200 not in content


@pytest.mark.asyncio
async def test_run_local_psychology_context_records_failure_summary() -> None:
    response = MagicMock()
    response.status_code = 503
    response.text = "sidecar overloaded " * 100
    response.raise_for_status.side_effect = RuntimeError("service unavailable")
    client = _AsyncClientStub(response)

    with patch.object(local_psychology_runtime.settings, "local_psychology_base_url", "http://127.0.0.1:19400/v1"), \
         patch.object(local_psychology_runtime.settings, "local_psychology_model", "psychology_model_suite"), \
         patch("agentic_capital.adapters.llm.local_psychology_runtime.httpx.AsyncClient", return_value=client):
        result = await local_psychology_runtime.run_local_psychology_context(
            request_id="cycle-1",
            agent_context={"agent_id": "CEO-Alpha"},
            input_text="trace",
        )

    assert result["ok"] is False
    assert result["status_code"] == 503
    assert result["error"] == "RuntimeError"
    assert result["failure_body_summary"].startswith("sidecar overloaded")
    assert len(result["failure_body_summary"]) <= 503


def test_psychology_payload_requires_stable_soft_signal_schema() -> None:
    with pytest.raises(local_psychology_runtime.LocalPsychologyRuntimeError, match="schema_missing_required"):
        local_psychology_runtime.validate_psychology_context_payload({
            "evidence_ids": [],
            "confidence": 0.5,
            "uncertainty": [],
        })


@pytest.mark.parametrize(
    "payload,error",
    [
        (
            {
                "action": "BUY",
                "evidence_ids": [],
                "confidence": 0.5,
                "uncertainty": [],
                "risk_tags": [],
                "allowed_downstream_use": "context_only",
            },
            "trade_action_leak",
        ),
        (
            {
                "evidence_ids": [],
                "confidence": 0.5,
                "uncertainty": [],
                "risk_tags": [],
                "allowed_downstream_use": "trade_decision",
            },
            "disallowed_downstream_use",
        ),
        (
            {
                "evidence_ids": [],
                "confidence": 1.7,
                "uncertainty": [],
                "risk_tags": [],
                "allowed_downstream_use": "context_only",
            },
            "confidence_out_of_bounds",
        ),
        (
            {
                "evidence_ids": [],
                "confidence": 0.4,
                "uncertainty": ["진단 필요"],
                "risk_tags": [],
                "allowed_downstream_use": "context_only",
            },
            "clinical_claim",
        ),
    ],
)
def test_psychology_payload_rejects_runtime_boundary_violations(payload, error) -> None:
    with pytest.raises(local_psychology_runtime.LocalPsychologyRuntimeError, match=error):
        local_psychology_runtime.validate_psychology_context_payload(payload)


def test_psychology_payload_allows_negated_order_safety_language() -> None:
    result = local_psychology_runtime.validate_psychology_context_payload({
        "evidence_ids": ["runtime_schema_contract.md"],
        "confidence": 0.0,
        "uncertainty": ["model must not execute capital order without session transition signal"],
        "risk_tags": ["pre_market_missing_context"],
        "allowed_downstream_use": "context_only",
    })

    assert result["allowed_downstream_use"] == "context_only"
    assert result["evidence_count"] == 1


def test_psychology_payload_still_rejects_direct_order_instruction() -> None:
    with pytest.raises(local_psychology_runtime.LocalPsychologyRuntimeError, match="order_instruction_leak"):
        local_psychology_runtime.validate_psychology_context_payload({
            "evidence_ids": ["runtime_schema_contract.md"],
            "confidence": 0.0,
            "uncertainty": ["execute order now"],
            "risk_tags": ["unsafe_instruction"],
            "allowed_downstream_use": "context_only",
        })


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
    assert "allowed_downstream_use=context_only" in request_payload["messages"][0]["content"]


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
    assert result["schema_status"] == "schema_repaired_context_only"
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
