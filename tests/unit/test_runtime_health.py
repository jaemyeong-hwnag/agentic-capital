"""Tests for runtime health checks."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_capital.monitoring import runtime_health


def test_local_agent_health_checks_agent_runtime_url() -> None:
    response = MagicMock()
    response.json.return_value = {"ok": True, "model": "agentic_capital_react_model"}
    response.raise_for_status.return_value = None

    with patch.object(runtime_health, "is_local_llm_enabled", return_value=True), \
         patch.object(runtime_health.settings, "local_agent_llm_base_url", "http://127.0.0.1:19000/v1"), \
         patch.object(runtime_health.settings, "local_agent_llm_model", "agentic_capital_react_model"), \
         patch("agentic_capital.monitoring.runtime_health.httpx.get", return_value=response) as mock_get:
        result = runtime_health.check_local_agent_health()

    assert result["ok"] is True
    assert result["actual_model"] == "agentic_capital_react_model"
    mock_get.assert_called_once_with("http://127.0.0.1:19000/healthz", timeout=5.0)


def test_local_agent_health_falls_back_to_llama_health_endpoint() -> None:
    not_found = MagicMock()
    not_found.raise_for_status.side_effect = http_error = RuntimeError("404")
    ok = MagicMock()
    ok.json.return_value = {"status": "ok"}
    ok.raise_for_status.return_value = None

    with patch.object(runtime_health, "is_local_llm_enabled", return_value=True), \
         patch.object(runtime_health.settings, "local_agent_llm_base_url", "http://127.0.0.1:19000/v1"), \
         patch.object(runtime_health.settings, "local_agent_llm_model", "agentic_capital_react_model"), \
         patch(
             "agentic_capital.monitoring.runtime_health.httpx.get",
             side_effect=[not_found, ok],
         ) as mock_get:
        result = runtime_health.check_local_agent_health()

    assert http_error
    assert result["ok"] is True
    assert result["health_url"] == "http://127.0.0.1:19000/health"
    assert mock_get.call_args_list[0].args[0] == "http://127.0.0.1:19000/healthz"
    assert mock_get.call_args_list[1].args[0] == "http://127.0.0.1:19000/health"


def test_finance_sidecar_health_reports_pipeline_failure() -> None:
    with patch(
        "agentic_capital.monitoring.runtime_health.check_local_finance_health",
        return_value={"ok": True, "actual_model": "finance_decision_model"},
    ), patch(
        "agentic_capital.monitoring.runtime_health.check_local_finance_pipeline_health",
        side_effect=RuntimeError("risk guard down"),
    ):
        result = runtime_health.check_finance_sidecar_health()

    assert result["ok"] is False
    assert result["pipeline"]["name"] == "finance_pipeline"
    assert "risk guard down" in result["pipeline"]["message"]


@pytest.mark.asyncio
async def test_collect_runtime_health_aggregates_services() -> None:
    with patch(
        "agentic_capital.monitoring.runtime_health.check_local_agent_health",
        return_value={"name": "agent_llm", "ok": True},
    ), patch(
        "agentic_capital.monitoring.runtime_health.check_finance_sidecar_health",
        return_value={"name": "finance_sidecars", "ok": True},
    ), patch(
        "agentic_capital.monitoring.runtime_health.check_psychology_sidecar_health",
        return_value={"name": "psychology_sidecar", "ok": True},
    ), patch(
        "agentic_capital.monitoring.runtime_health.check_database_health",
        new=AsyncMock(return_value={"name": "database", "ok": True}),
    ), patch.object(
        runtime_health.settings,
        "local_model_inventory_healthcheck_enabled",
        False,
    ):
        result = await runtime_health.collect_runtime_health()

    assert result["ok"] is True
    assert [check["name"] for check in result["checks"]] == [
        "agent_llm",
        "finance_sidecars",
        "psychology_sidecar",
        "database",
    ]


@pytest.mark.asyncio
async def test_collect_runtime_health_ignores_nonblocking_inventory_for_overall_ok() -> None:
    with patch(
        "agentic_capital.monitoring.runtime_health.check_local_agent_health",
        return_value={"name": "agent_llm", "ok": True},
    ), patch(
        "agentic_capital.monitoring.runtime_health.check_finance_sidecar_health",
        return_value={"name": "finance_sidecars", "ok": True},
    ), patch(
        "agentic_capital.monitoring.runtime_health.check_psychology_sidecar_health",
        return_value={"name": "psychology_sidecar", "ok": True},
    ), patch(
        "agentic_capital.monitoring.runtime_health.check_database_health",
        new=AsyncMock(return_value={"name": "database", "ok": True}),
    ), patch.object(
        runtime_health.settings,
        "local_model_inventory_healthcheck_enabled",
        True,
    ), patch(
        "agentic_capital.monitoring.runtime_health.check_model_inventory_health",
        return_value={"name": "local_model_inventory", "ok": False, "blocking": False},
    ):
        result = await runtime_health.collect_runtime_health()

    assert result["ok"] is True
    assert result["checks"][-1] == {"name": "local_model_inventory", "ok": False, "blocking": False}


def test_model_inventory_reports_unvalidated_non_runtime_models() -> None:
    result = runtime_health.check_model_inventory_health(
        {
            "name": "finance_sidecars",
            "ok": True,
            "primary": {"ok": True, "actual_model": "finance_decision_model"},
            "pipeline": {
                "ok": True,
                "stages": {
                    "finance_rag_query_model": {
                        "ok": True,
                        "actual_model": "finance_rag_query_model",
                    },
                    "finance_tool_planner_model": {
                        "ok": True,
                        "actual_model": "finance_tool_planner_model",
                    },
                    "finance_decision_model": {"ok": True, "actual_model": "finance_decision_model"},
                    "finance_risk_guard_model": {"ok": True, "actual_model": "finance_risk_guard_model"},
                },
            },
        },
        {"name": "psychology_sidecar", "ok": True, "actual_model": "psychology_model_suite"},
    )

    assert result["ok"] is False
    assert "finance_embedding_model" in result["unvalidated_models"]
    assert "psychology_profile_model" in result["unvalidated_models"]
    assert next(
        item for item in result["finance_models"] if item["name"] == "finance_decision_model"
    )["coverage"] == "paper_runtime_sidecar"
    assert next(
        item for item in result["psychology_models"] if item["name"] == "psychology_profile_model"
    )["coverage"] == "suite_only"


def test_model_inventory_checks_configured_validation_sidecar() -> None:
    response = MagicMock()
    response.json.return_value = {"ok": True, "model": "finance_embedding_model"}
    response.raise_for_status.return_value = None

    with patch.object(
        runtime_health.settings,
        "local_finance_validation_base_urls",
        "finance_embedding_model=http://127.0.0.1:18105/v1",
    ), patch.object(
        runtime_health.settings,
        "local_psychology_validation_base_urls",
        "",
    ), patch(
        "agentic_capital.monitoring.runtime_health.httpx.get",
        return_value=response,
    ) as mock_get:
        result = runtime_health.check_model_inventory_health(
            {"name": "finance_sidecars", "ok": True, "primary": {}, "pipeline": {"stages": {}}},
            {"name": "psychology_sidecar", "ok": False},
        )

    embedding = next(
        item for item in result["finance_models"] if item["name"] == "finance_embedding_model"
    )
    assert embedding["ok"] is True
    assert embedding["coverage"] == "validation_sidecar"
    mock_get.assert_called_once_with("http://127.0.0.1:18105/healthz", timeout=5.0)
