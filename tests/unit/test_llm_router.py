"""Tests for LLM provider router."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_capital import local_finance_smoke
from agentic_capital.adapters.llm import local_finance_runtime, router


def test_local_provider_names_enable_local_mode():
    with patch.object(router.settings, "llm_provider", "domain_llm_forge"):
        assert router.is_local_llm_enabled() is True


def test_router_builds_local_langchain_model():
    with patch.object(router.settings, "llm_provider", "local"), \
         patch.object(router.settings, "local_llm_base_url", "http://127.0.0.1:8080/v1"), \
         patch.object(router.settings, "local_llm_model", "finance_decision_model"), \
         patch.object(router.settings, "local_agent_llm_base_url", "http://127.0.0.1:19000/v1"), \
         patch.object(router.settings, "local_agent_llm_model", "agentic_capital_react_model"), \
         patch.object(router.settings, "local_llm_api_key", ""), \
         patch.object(router.settings, "local_llm_timeout_seconds", 10.0), \
         patch.object(router.settings, "local_llm_temperature", 0.2), \
         patch.object(router.settings, "local_llm_send_native_tools", False):
        model = router.build_langchain_chat_model()

    assert model.model == "agentic_capital_react_model"
    assert model.base_url == "http://127.0.0.1:19000/v1"
    assert model.send_native_tools is False


def test_router_rejects_finance_model_as_general_agent_llm():
    with patch.object(router.settings, "llm_provider", "local"), \
         patch.object(router.settings, "local_llm_model", "finance_decision_model"), \
         patch.object(router.settings, "local_agent_llm_model", ""), \
         pytest.raises(ValueError, match="LOCAL_AGENT_LLM_MODEL"):
        router.build_langchain_chat_model()


def test_router_requires_agent_base_url_when_finance_model_is_primary():
    with patch.object(router.settings, "llm_provider", "local"), \
         patch.object(router.settings, "local_llm_model", "finance_decision_model"), \
         patch.object(router.settings, "local_agent_llm_model", "agentic_capital_react_model"), \
         patch.object(router.settings, "local_agent_llm_base_url", ""), \
         pytest.raises(ValueError, match="LOCAL_AGENT_LLM_BASE_URL"):
        router.build_langchain_chat_model()


def test_router_uses_gemini_only_when_explicitly_configured():
    with patch.object(router.settings, "llm_provider", "gemini"), \
         patch("langchain_google_genai.ChatGoogleGenerativeAI", return_value=MagicMock()) as mock_cls:
        router.build_langchain_chat_model()

    mock_cls.assert_called_once()


def test_router_rejects_unknown_provider_instead_of_falling_back_to_gemini():
    with patch.object(router.settings, "llm_provider", "gemni"), \
         pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
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
         patch("agentic_capital.adapters.llm.local_finance_runtime.httpx.get", return_value=response), \
         pytest.raises(local_finance_runtime.LocalFinanceRuntimeError, match="model_category_mismatch"):
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


def test_finance_smoke_rejects_buy_with_fabricated_evidence_but_no_tool_results():
    with pytest.raises(local_finance_runtime.LocalFinanceRuntimeError, match="trade_missing_tool_results"):
        local_finance_runtime.validate_finance_decision_payload({
            "action": "BUY",
            "symbol": "005930",
            "quantity": 1,
            "evidence_ids": ["ev-fabricated"],
            "required_tools": ["get_balance", "get_positions", "get_quote", "get_market_session", "get_risk_limit", "search_rag"],
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


def test_local_finance_stage_base_urls_default_to_primary_base_url():
    with patch.object(local_finance_runtime.settings, "local_llm_base_url", "http://127.0.0.1:8080/v1"), \
         patch.object(local_finance_runtime.settings, "local_finance_rag_query_base_url", ""), \
         patch.object(local_finance_runtime.settings, "local_finance_tool_planner_base_url", ""), \
         patch.object(local_finance_runtime.settings, "local_finance_decision_base_url", ""), \
         patch.object(local_finance_runtime.settings, "local_finance_risk_guard_base_url", ""):
        assert (
            local_finance_runtime._chat_url(local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL)
            == "http://127.0.0.1:8080/v1/chat/completions"
        )


def test_local_finance_stage_base_urls_route_to_individual_sidecars():
    with patch.object(local_finance_runtime.settings, "local_llm_base_url", "http://127.0.0.1:8080/v1"), \
         patch.object(local_finance_runtime.settings, "local_finance_rag_query_base_url", "http://127.0.0.1:18101/v1"), \
         patch.object(local_finance_runtime.settings, "local_finance_tool_planner_base_url", "http://127.0.0.1:18102/v1"), \
         patch.object(local_finance_runtime.settings, "local_finance_decision_base_url", "http://127.0.0.1:18103/v1"), \
         patch.object(local_finance_runtime.settings, "local_finance_risk_guard_base_url", "http://127.0.0.1:18104/v1"):
        assert (
            local_finance_runtime._chat_url(local_finance_runtime.FINANCE_RAG_QUERY_MODEL)
            == "http://127.0.0.1:18101/v1/chat/completions"
        )
        assert (
            local_finance_runtime._chat_url(local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL)
            == "http://127.0.0.1:18102/v1/chat/completions"
        )
        assert (
            local_finance_runtime._chat_url(local_finance_runtime.FINANCE_DECISION_MODEL)
            == "http://127.0.0.1:18103/v1/chat/completions"
        )
        assert (
            local_finance_runtime._chat_url(local_finance_runtime.FINANCE_RISK_GUARD_MODEL)
            == "http://127.0.0.1:18104/v1/chat/completions"
        )


def test_local_finance_pipeline_health_skips_unconfigured_stage_urls():
    with patch.object(local_finance_runtime.settings, "local_finance_rag_query_base_url", ""), \
         patch.object(local_finance_runtime.settings, "local_finance_tool_planner_base_url", ""), \
         patch.object(local_finance_runtime.settings, "local_finance_decision_base_url", ""), \
         patch.object(local_finance_runtime.settings, "local_finance_risk_guard_base_url", ""), \
         patch("agentic_capital.adapters.llm.local_finance_runtime.httpx.get") as mock_get:
        result = local_finance_runtime.check_local_finance_pipeline_health()

    assert result == {"ok": True, "checked": 0, "stages": {}}
    mock_get.assert_not_called()


def test_local_finance_pipeline_health_checks_configured_stage_sidecars():
    def fake_get(url, timeout):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "ok": True,
            "model": {
                "http://127.0.0.1:18101/healthz": local_finance_runtime.FINANCE_RAG_QUERY_MODEL,
                "http://127.0.0.1:18102/healthz": local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL,
                "http://127.0.0.1:18104/healthz": local_finance_runtime.FINANCE_RISK_GUARD_MODEL,
            }[url],
            "llama_reachable": True,
        }
        return response

    with patch.object(local_finance_runtime.settings, "local_finance_rag_query_base_url", "http://127.0.0.1:18101/v1"), \
         patch.object(local_finance_runtime.settings, "local_finance_tool_planner_base_url", "http://127.0.0.1:18102/v1"), \
         patch.object(local_finance_runtime.settings, "local_finance_decision_base_url", ""), \
         patch.object(local_finance_runtime.settings, "local_finance_risk_guard_base_url", "http://127.0.0.1:18104/v1"), \
         patch.object(local_finance_runtime.settings, "local_llm_health_timeout_seconds", 2.0), \
         patch("agentic_capital.adapters.llm.local_finance_runtime.httpx.get", side_effect=fake_get) as mock_get:
        result = local_finance_runtime.check_local_finance_pipeline_health()

    assert result["ok"] is True
    assert result["checked"] == 3
    assert set(result["stages"]) == {
        local_finance_runtime.FINANCE_RAG_QUERY_MODEL,
        local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL,
        local_finance_runtime.FINANCE_RISK_GUARD_MODEL,
    }
    assert mock_get.call_count == 3


def test_local_finance_pipeline_health_rejects_mismatched_stage_model():
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "ok": True,
        "model": local_finance_runtime.FINANCE_DECISION_MODEL,
        "llama_reachable": True,
    }

    with patch.object(local_finance_runtime.settings, "local_finance_rag_query_base_url", ""), \
         patch.object(local_finance_runtime.settings, "local_finance_tool_planner_base_url", "http://127.0.0.1:18102/v1"), \
         patch.object(local_finance_runtime.settings, "local_finance_decision_base_url", ""), \
         patch.object(local_finance_runtime.settings, "local_finance_risk_guard_base_url", ""), \
         patch("agentic_capital.adapters.llm.local_finance_runtime.httpx.get", return_value=response), \
         pytest.raises(local_finance_runtime.LocalFinanceRuntimeError, match="local_llm_model_mismatch"):
        local_finance_runtime.check_local_finance_pipeline_health()


def test_validate_local_finance_runtime_reports_pipeline_health():
    with patch.object(local_finance_runtime.settings, "local_llm_readiness_required", True), \
         patch.object(local_finance_runtime.settings, "local_finance_smoke_enabled", False), \
         patch(
             "agentic_capital.adapters.llm.local_finance_runtime.check_local_finance_health",
             return_value={"actual_model": local_finance_runtime.FINANCE_DECISION_MODEL, "ok": True},
         ), \
         patch(
             "agentic_capital.adapters.llm.local_finance_runtime.check_local_finance_pipeline_health",
             return_value={
                 "ok": True,
                 "checked": 1,
                 "stages": {local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL: {"ok": True}},
             },
         ):
        result = local_finance_runtime.validate_local_finance_runtime()

    assert result["ok"] is True
    assert result["pipeline_health"]["checked"] == 1
    assert result["smoke"] == {"skipped": True}


@pytest.mark.asyncio
async def test_local_finance_decision_pipeline_records_raw_failure_on_no_context():
    async def collect_tool_results(payload):
        return {
            "get_balance": {"available": 1000000},
            "get_positions": [],
            "get_quote": {"price": 70000},
            "get_market_session": {"state": "regular", "is_open": True, "regular_session": True},
            "get_risk_limit": {"max_order_value": 1000000},
            "search_rag": {"evidence_ids": [], "evidence_count": 0},
        }

    async def fake_stage(*, model, payload, system):
        if model == local_finance_runtime.FINANCE_RAG_QUERY_MODEL:
            return {"queries": ["005930 risk check"]}, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL:
            return {"tool_plan": ["get_balance", "get_positions"]}, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_DECISION_MODEL:
            return {"action": "NO_CONTEXT", "reason": "근거 부족"}, {"model": model, "latency_ms": 1, "ok": True}
        return {"risk_flags": ["missing_context"], "hard_fail": False}, {"model": model, "latency_ms": 1, "ok": True}

    with patch(
        "agentic_capital.adapters.llm.local_finance_runtime._call_finance_stage",
        AsyncMock(side_effect=fake_stage),
    ), patch(
        "agentic_capital.adapters.llm.local_finance_runtime._search_rag",
        AsyncMock(return_value=([], {"model": "rag_search", "latency_ms": 1, "ok": True})),
    ):
        result = await local_finance_runtime.run_local_finance_decision_pipeline(
            request_id="req-1",
            user_question="005930 매수 가능?",
            agent_state={"deployment_mode": "paper", "live_order_enabled": False, "symbol": "005930"},
            required_safety={"stop_on_missing_context": True},
            collect_tool_results=collect_tool_results,
        )

    assert result["record_type"] == "raw_model_failure"
    assert result["record"]["failure_type"] == "no_context"
    assert result["decision"]["action"] == "NO_CONTEXT"
    assert result["risk_flags"] == ["missing_context"]


@pytest.mark.asyncio
async def test_local_finance_tool_planner_uses_compact_evidence_and_fallback():
    captured_planner_payload = {}
    captured_decision_payload = {}
    captured_risk_payload = {}

    async def collect_tool_results(payload):
        assert payload["tool_plan"]["fallback"] == "deterministic_paper_tool_plan"
        return {
            "get_balance": {"available": 1_000_000, "currency": "KRW"},
            "get_positions": [],
            "get_quote": {"price": 70_000, "symbol": "005930", "market": "kr_stock"},
            "get_market_session": {"state": "regular", "is_open": True, "regular_session": True},
            "get_risk_limit": {"max_order_value": 1_000_000},
            "search_rag": {
                "evidence_ids": payload["evidence_ids"],
                "evidence_count": len(payload["evidence"]),
                "evidence": [{"doc_id": "ev-raw", "text": "y" * 2000}],
            },
            "finance_decision_payload": {
                "balance": {"available": 1_000_000, "currency": "KRW"},
                "positions": [],
                "quote": {"price": 70_000, "symbol": "005930", "market": "kr_stock"},
                "market_session": {"state": "regular", "is_open": True, "regular_session": True},
                "risk_limit": {"max_order_value": 1_000_000},
                "rag": {"evidence": [{"doc_id": "ev-raw", "text": "z" * 2000}]},
            },
        }

    async def fake_stage(*, model, payload, system):
        if model == local_finance_runtime.FINANCE_RAG_QUERY_MODEL:
            return {"queries": ["005930 risk check"], "symbol": "005930"}, {
                "model": model,
                "stage": model,
                "latency_ms": 1,
                "ok": True,
            }
        if model == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL:
            captured_planner_payload.update(payload)
            raise local_finance_runtime.LocalFinanceStageError(
                model,
                "planner unavailable",
                status_code=503,
                body_summary="service unavailable",
                latency_ms=7,
                compact_payload_hash="plannerhash",
            )
        if model == local_finance_runtime.FINANCE_DECISION_MODEL:
            captured_decision_payload.update(payload)
            assert payload["finance_context"]["balance"]["available"] == 1_000_000
            assert payload["tool_results"]["available"] == sorted([
                "finance_decision_payload",
                "get_balance",
                "get_market_session",
                "get_positions",
                "get_quote",
                "get_risk_limit",
                "search_rag",
            ])
            assert "tool_results" not in payload["finance_context"]
            assert len(payload["user_question"]) < 350
            return {
                "action": "CALL_TOOL",
                "symbol": "005930",
                "market": "kr_stock",
                "required_tools": [
                    "search_rag",
                    "get_balance",
                    "get_positions",
                    "get_quote",
                    "get_market_session",
                    "get_risk_limit",
                ],
                "evidence_ids": ["ev-compact"],
            }, {"model": model, "stage": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_RISK_GUARD_MODEL:
            captured_risk_payload.update(payload)
            return {"risk_flags": [], "hard_fail": False}, {"model": model, "stage": model, "latency_ms": 1, "ok": True}
        return {"risk_flags": [], "hard_fail": False}, {"model": model, "stage": model, "latency_ms": 1, "ok": True}

    with patch(
        "agentic_capital.adapters.llm.local_finance_runtime._call_finance_stage",
        AsyncMock(side_effect=fake_stage),
    ), patch(
        "agentic_capital.adapters.llm.local_finance_runtime._search_rag",
        AsyncMock(return_value=(
            [{
                "doc_id": "ev-compact",
                "source": "policy.md",
                "text": "x" * 2000,
                "score": 0.9,
            }],
            {"model": "rag_search", "stage": "rag_search", "latency_ms": 1, "ok": True},
        )),
    ):
        result = await local_finance_runtime.run_local_finance_decision_pipeline(
            request_id="req-planner-fallback",
            user_question="005930 매수 가능?",
            agent_state={"deployment_mode": "paper", "live_order_enabled": False, "symbol": "005930"},
            required_safety={"paper_trade_only": True},
            collect_tool_results=collect_tool_results,
        )

    assert result["record_type"] == "finance_paper_shadow_decision"
    assert result["first_failing_stage"] == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL
    assert result["tool_plan"]["fallback"] == "deterministic_paper_tool_plan"
    assert captured_planner_payload["evidence_count"] == 1
    assert captured_planner_payload["evidence"][0]["preview"].endswith("...")
    assert "x" * 1000 not in json.dumps(captured_planner_payload, ensure_ascii=False)
    assert captured_decision_payload["evidence"][0]["preview"].endswith("...")
    assert "x" * 1000 not in json.dumps(captured_decision_payload, ensure_ascii=False)
    assert "y" * 1000 not in json.dumps(captured_decision_payload, ensure_ascii=False)
    assert "z" * 1000 not in json.dumps(captured_decision_payload, ensure_ascii=False)
    assert "rag_query" not in captured_risk_payload
    assert "tool_plan" not in captured_risk_payload
    assert "evidence" not in captured_risk_payload
    assert captured_risk_payload["finance_context"]["rag"]["evidence_ids"] == []
    assert "y" * 1000 not in json.dumps(captured_risk_payload, ensure_ascii=False)
    assert "z" * 1000 not in json.dumps(captured_risk_payload, ensure_ascii=False)
    failed_stage = next(call for call in result["sidecar_calls"] if call.get("ok") is False)
    assert failed_stage["status_code"] == 503
    assert failed_stage["failure_body_summary"] == "service unavailable"


@pytest.mark.asyncio
async def test_local_finance_decision_pipeline_blocks_buy_over_risk_limit():
    async def collect_tool_results(payload):
        return {
            "get_balance": {"available": 1_000_000, "currency": "KRW"},
            "get_positions": [],
            "get_quote": {"price": 70_000, "symbol": "005930", "market": "kr_stock"},
            "get_market_session": {"state": "regular", "is_open": True, "regular_session": True},
            "get_risk_limit": {"max_order_value": 300_000},
            "search_rag": {
                "evidence_ids": payload["evidence_ids"],
                "evidence_count": len(payload["evidence"]),
            },
        }

    async def fake_stage(*, model, payload, system):
        if model == local_finance_runtime.FINANCE_RAG_QUERY_MODEL:
            return {
                "query": "005930 지금 매수?",
                "queries": ["005930 지금 매수?"],
                "symbol": "005930",
                "market": "kr_stock",
                "route": "rag_and_fresh_quote",
                "requires_fresh_data": True,
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL:
            return {
                "tool_plan": [
                    {"tool": "search_rag"},
                    {"tool": "get_market_session"},
                    {"tool": "get_balance"},
                    {"tool": "get_positions"},
                    {"tool": "get_quote"},
                    {"tool": "get_risk_limit"},
                ],
                "forbidden_tools": ["submit_order"],
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_DECISION_MODEL:
            return {
                "action": "BUY",
                "symbol": "005930",
                "market": "kr_stock",
                "quantity": 10,
                "confidence": 0.42,
                "required_tools": [
                    "search_rag",
                    "get_balance",
                    "get_positions",
                    "get_quote",
                    "get_market_session",
                    "get_risk_limit",
                ],
                "evidence_ids": ["decision_policy.md"],
                "reason": "paper shadow candidate only",
            }, {"model": model, "latency_ms": 1, "ok": True}
        return {"risk_flags": [], "hard_fail": False}, {"model": model, "latency_ms": 1, "ok": True}

    with patch(
        "agentic_capital.adapters.llm.local_finance_runtime._call_finance_stage",
        AsyncMock(side_effect=fake_stage),
    ), patch(
        "agentic_capital.adapters.llm.local_finance_runtime._search_rag",
        AsyncMock(return_value=(
            [{"doc_id": "decision_policy.md", "text": "risk limit and evidence contract"}],
            {"model": "rag_search", "latency_ms": 1, "ok": True},
        )),
    ):
        result = await local_finance_runtime.run_local_finance_decision_pipeline(
            request_id="req-risk",
            user_question="005930 지금 매수?",
            agent_state={"deployment_mode": "paper", "live_order_enabled": False, "symbol": "005930"},
            required_safety={"paper_trade_only": True, "require_evidence_ids": True},
            collect_tool_results=collect_tool_results,
        )

    assert result["ok"] is False
    assert result["record_type"] == "raw_model_failure"
    assert result["record"]["failure_type"] == "trade_exceeds_risk_limit"
    assert result["record"]["retrain_candidate"] is True
    assert result["record"]["details"]["notional"] == 700_000
    assert result["decision"]["action"] == "BUY"
    assert result["record"]["evidence_ids"] == ["decision_policy.md"]


@pytest.mark.asyncio
async def test_local_finance_decision_pipeline_uses_quote_price_over_model_price():
    async def collect_tool_results(payload):
        return {
            "get_balance": {"available": 1_000_000, "currency": "KRW"},
            "get_positions": [],
            "get_quote": {"price": 70_000, "symbol": "005930", "market": "kr_stock"},
            "get_market_session": {"state": "regular", "is_open": True, "regular_session": True},
            "get_risk_limit": {"max_order_value": 300_000},
            "search_rag": {
                "evidence_ids": payload["evidence_ids"],
                "evidence_count": len(payload["evidence"]),
            },
        }

    async def fake_stage(*, model, payload, system):
        if model == local_finance_runtime.FINANCE_RAG_QUERY_MODEL:
            return {
                "query": "005930 가격 조작 매수?",
                "queries": ["005930 가격 조작 매수?"],
                "symbol": "005930",
                "market": "kr_stock",
                "route": "rag_and_fresh_quote",
                "requires_fresh_data": True,
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL:
            return {
                "tool_plan": [
                    {"tool": "search_rag"},
                    {"tool": "get_market_session"},
                    {"tool": "get_balance"},
                    {"tool": "get_positions"},
                    {"tool": "get_quote"},
                    {"tool": "get_risk_limit"},
                ]
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_DECISION_MODEL:
            return {
                "action": "BUY",
                "symbol": "005930",
                "market": "kr_stock",
                "quantity": 10,
                "price": 1,
                "required_tools": [
                    "search_rag",
                    "get_balance",
                    "get_positions",
                    "get_quote",
                    "get_market_session",
                    "get_risk_limit",
                ],
                "evidence_ids": ["decision_policy.md"],
                "reason": "paper shadow candidate with stale model price",
            }, {"model": model, "latency_ms": 1, "ok": True}
        return {"risk_flags": [], "hard_fail": False}, {"model": model, "latency_ms": 1, "ok": True}

    with patch(
        "agentic_capital.adapters.llm.local_finance_runtime._call_finance_stage",
        AsyncMock(side_effect=fake_stage),
    ), patch(
        "agentic_capital.adapters.llm.local_finance_runtime._search_rag",
        AsyncMock(return_value=(
            [{"doc_id": "decision_policy.md", "text": "tool quote price is authoritative"}],
            {"model": "rag_search", "latency_ms": 1, "ok": True},
        )),
    ):
        result = await local_finance_runtime.run_local_finance_decision_pipeline(
            request_id="req-quote-price",
            user_question="005930 모델 가격이 낮으면 매수?",
            agent_state={"deployment_mode": "paper", "live_order_enabled": False, "symbol": "005930"},
            required_safety={"paper_trade_only": True, "require_evidence_ids": True},
            collect_tool_results=collect_tool_results,
        )

    assert result["ok"] is False
    assert result["record_type"] == "raw_model_failure"
    assert result["record"]["failure_type"] == "trade_exceeds_risk_limit"
    assert result["record"]["retrain_candidate"] is True
    assert result["record"]["details"]["notional"] == 700_000
    assert result["record"]["evidence_ids"] == ["decision_policy.md"]


@pytest.mark.asyncio
async def test_local_finance_decision_pipeline_blocks_mismatched_quote_symbol():
    async def collect_tool_results(payload):
        return {
            "get_balance": {"available": 1_000_000, "currency": "KRW"},
            "get_positions": [],
            "get_quote": {"price": 70_000, "symbol": "000660", "market": "kr_stock"},
            "get_market_session": {"state": "regular", "is_open": True, "regular_session": True},
            "get_risk_limit": {"max_order_value": 1_000_000},
            "search_rag": {
                "evidence_ids": payload["evidence_ids"],
                "evidence_count": len(payload["evidence"]),
            },
        }

    async def fake_stage(*, model, payload, system):
        if model == local_finance_runtime.FINANCE_RAG_QUERY_MODEL:
            return {
                "query": "005930 다른 quote 매수?",
                "queries": ["005930 다른 quote 매수?"],
                "symbol": "005930",
                "market": "kr_stock",
                "route": "rag_and_fresh_quote",
                "requires_fresh_data": True,
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL:
            return {
                "tool_plan": [
                    {"tool": "search_rag"},
                    {"tool": "get_market_session"},
                    {"tool": "get_balance"},
                    {"tool": "get_positions"},
                    {"tool": "get_quote"},
                    {"tool": "get_risk_limit"},
                ]
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_DECISION_MODEL:
            return {
                "action": "BUY",
                "symbol": "005930",
                "market": "kr_stock",
                "quantity": 1,
                "required_tools": [
                    "search_rag",
                    "get_balance",
                    "get_positions",
                    "get_quote",
                    "get_market_session",
                    "get_risk_limit",
                ],
                "evidence_ids": ["decision_policy.md"],
                "reason": "paper shadow candidate with mismatched quote",
            }, {"model": model, "latency_ms": 1, "ok": True}
        return {"risk_flags": [], "hard_fail": False}, {"model": model, "latency_ms": 1, "ok": True}

    with patch(
        "agentic_capital.adapters.llm.local_finance_runtime._call_finance_stage",
        AsyncMock(side_effect=fake_stage),
    ), patch(
        "agentic_capital.adapters.llm.local_finance_runtime._search_rag",
        AsyncMock(return_value=(
            [{"doc_id": "decision_policy.md", "text": "quote symbol must match decision symbol"}],
            {"model": "rag_search", "latency_ms": 1, "ok": True},
        )),
    ):
        result = await local_finance_runtime.run_local_finance_decision_pipeline(
            request_id="req-quote-mismatch",
            user_question="005930 quote가 다르면 매수?",
            agent_state={"deployment_mode": "paper", "live_order_enabled": False, "symbol": "005930"},
            required_safety={"paper_trade_only": True, "require_evidence_ids": True},
            collect_tool_results=collect_tool_results,
        )

    assert result["ok"] is False
    assert result["record_type"] == "raw_model_failure"
    assert result["record"]["failure_type"] == "trade_quote_context_mismatch"
    assert result["record"]["retrain_candidate"] is True
    assert result["record"]["details"]["symbol"] == {"expected": "005930", "actual": "000660"}
    assert result["record"]["evidence_ids"] == ["decision_policy.md"]


@pytest.mark.asyncio
async def test_local_finance_decision_pipeline_blocks_buy_over_available_cash():
    async def collect_tool_results(payload):
        return {
            "get_balance": {"available": 100_000, "currency": "KRW"},
            "get_positions": [],
            "get_quote": {"price": 70_000, "symbol": "005930", "market": "kr_stock"},
            "get_market_session": {"state": "regular", "is_open": True, "regular_session": True},
            "get_risk_limit": {"max_order_value": 1_000_000},
            "search_rag": {
                "evidence_ids": payload["evidence_ids"],
                "evidence_count": len(payload["evidence"]),
            },
        }

    async def fake_stage(*, model, payload, system):
        if model == local_finance_runtime.FINANCE_RAG_QUERY_MODEL:
            return {
                "query": "005930 현금보다 많이 매수?",
                "queries": ["005930 현금보다 많이 매수?"],
                "symbol": "005930",
                "market": "kr_stock",
                "route": "rag_and_fresh_quote",
                "requires_fresh_data": True,
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL:
            return {
                "tool_plan": [
                    {"tool": "search_rag"},
                    {"tool": "get_market_session"},
                    {"tool": "get_balance"},
                    {"tool": "get_positions"},
                    {"tool": "get_quote"},
                    {"tool": "get_risk_limit"},
                ],
                "forbidden_tools": ["submit_order"],
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_DECISION_MODEL:
            return {
                "action": "BUY",
                "symbol": "005930",
                "market": "kr_stock",
                "quantity": 3,
                "required_tools": [
                    "search_rag",
                    "get_balance",
                    "get_positions",
                    "get_quote",
                    "get_market_session",
                    "get_risk_limit",
                ],
                "evidence_ids": ["cash_policy.md"],
                "reason": "paper shadow candidate only",
            }, {"model": model, "latency_ms": 1, "ok": True}
        return {"risk_flags": [], "hard_fail": False}, {"model": model, "latency_ms": 1, "ok": True}

    with patch(
        "agentic_capital.adapters.llm.local_finance_runtime._call_finance_stage",
        AsyncMock(side_effect=fake_stage),
    ), patch(
        "agentic_capital.adapters.llm.local_finance_runtime._search_rag",
        AsyncMock(return_value=(
            [{"doc_id": "cash_policy.md", "text": "buy notional must not exceed available cash"}],
            {"model": "rag_search", "latency_ms": 1, "ok": True},
        )),
    ):
        result = await local_finance_runtime.run_local_finance_decision_pipeline(
            request_id="req-cash",
            user_question="005930 현금보다 많이 매수?",
            agent_state={"deployment_mode": "paper", "live_order_enabled": False, "symbol": "005930"},
            required_safety={"paper_trade_only": True, "cash_available_required": True},
            collect_tool_results=collect_tool_results,
        )

    assert result["ok"] is False
    assert result["record_type"] == "raw_model_failure"
    assert result["record"]["failure_type"] == "trade_exceeds_available_cash"
    assert result["record"]["retrain_candidate"] is True
    assert result["record"]["details"]["available_cash"] == 100_000
    assert result["record"]["details"]["notional"] == 210_000
    assert result["record"]["action"] == "BUY"
    assert result["record"]["evidence_ids"] == ["cash_policy.md"]


@pytest.mark.asyncio
async def test_local_finance_decision_pipeline_learns_missing_buy_notional():
    async def collect_tool_results(payload):
        return {
            "get_balance": {"available": 1_000_000, "currency": "KRW"},
            "get_positions": [],
            "get_quote": {"price": 70_000, "symbol": "005930", "market": "kr_stock"},
            "get_market_session": {"state": "regular", "is_open": True, "regular_session": True},
            "get_risk_limit": {"max_order_value": 1_000_000},
            "search_rag": {
                "evidence_ids": payload["evidence_ids"],
                "evidence_count": len(payload["evidence"]),
            },
        }

    async def fake_stage(*, model, payload, system):
        if model == local_finance_runtime.FINANCE_RAG_QUERY_MODEL:
            return {
                "query": "005930 수량 없이 매수?",
                "queries": ["005930 수량 없이 매수?"],
                "symbol": "005930",
                "market": "kr_stock",
                "route": "rag_and_fresh_quote",
                "requires_fresh_data": True,
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL:
            return {
                "tool_plan": [
                    {"tool": "search_rag"},
                    {"tool": "get_market_session"},
                    {"tool": "get_balance"},
                    {"tool": "get_positions"},
                    {"tool": "get_quote"},
                    {"tool": "get_risk_limit"},
                ]
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_DECISION_MODEL:
            return {
                "action": "BUY",
                "symbol": "005930",
                "market": "kr_stock",
                "required_tools": [
                    "search_rag",
                    "get_balance",
                    "get_positions",
                    "get_quote",
                    "get_market_session",
                    "get_risk_limit",
                ],
                "evidence_ids": ["notional_policy.md"],
                "reason": "paper shadow candidate without order size",
            }, {"model": model, "latency_ms": 1, "ok": True}
        return {"risk_flags": [], "hard_fail": False}, {"model": model, "latency_ms": 1, "ok": True}

    with patch(
        "agentic_capital.adapters.llm.local_finance_runtime._call_finance_stage",
        AsyncMock(side_effect=fake_stage),
    ), patch(
        "agentic_capital.adapters.llm.local_finance_runtime._search_rag",
        AsyncMock(return_value=(
            [{"doc_id": "notional_policy.md", "text": "buy decisions must include quantity or notional"}],
            {"model": "rag_search", "latency_ms": 1, "ok": True},
        )),
    ):
        result = await local_finance_runtime.run_local_finance_decision_pipeline(
            request_id="req-notional",
            user_question="005930 수량 없이 매수?",
            agent_state={"deployment_mode": "paper", "live_order_enabled": False, "symbol": "005930"},
            required_safety={"paper_trade_only": True, "require_evidence_ids": True},
            collect_tool_results=collect_tool_results,
        )

    assert result["ok"] is False
    assert result["record_type"] == "raw_model_failure"
    assert result["record"]["failure_type"] == "trade_missing_notional"
    assert result["record"]["retrain_candidate"] is True
    assert result["record"]["action"] == "BUY"
    assert result["record"]["evidence_ids"] == ["notional_policy.md"]


@pytest.mark.asyncio
async def test_local_finance_decision_pipeline_records_order_tool_planner_failure():
    async def collect_tool_results(payload):
        return {
            "get_balance": {"available": 1_000_000, "currency": "KRW"},
            "get_positions": [],
            "get_quote": {"price": 70_000, "symbol": "005930", "market": "kr_stock"},
            "get_market_session": {"state": "regular", "is_open": True, "regular_session": True},
            "get_risk_limit": {"max_order_value": 1_000_000},
            "search_rag": {
                "evidence_ids": payload["evidence_ids"],
                "evidence_count": len(payload["evidence"]),
            },
            "_errors": [
                {
                    "tool": "tool_plan",
                    "error": "order_tool_blocked_in_shadow",
                    "tools": ["submit_order"],
                }
            ],
        }

    async def fake_stage(*, model, payload, system):
        if model == local_finance_runtime.FINANCE_RAG_QUERY_MODEL:
            return {
                "query": "005930 주문 실행까지 계획?",
                "queries": ["005930 주문 실행까지 계획?"],
                "symbol": "005930",
                "market": "kr_stock",
                "route": "rag_and_fresh_quote",
                "requires_fresh_data": True,
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL:
            return {
                "tool_plan": [
                    {"tool": "search_rag"},
                    {"tool": "get_market_session"},
                    {"tool": "get_balance"},
                    {"tool": "get_positions"},
                    {"tool": "get_quote"},
                    {"tool": "get_risk_limit"},
                    {"tool": "submit_order"},
                ],
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_DECISION_MODEL:
            return {
                "action": "CALL_TOOL",
                "symbol": "005930",
                "market": "kr_stock",
                "required_tools": [
                    "search_rag",
                    "get_balance",
                    "get_positions",
                    "get_quote",
                    "get_market_session",
                    "get_risk_limit",
                ],
                "evidence_ids": ["tool_policy.md"],
                "reason": "tool collection required",
            }, {"model": model, "latency_ms": 1, "ok": True}
        return {"risk_flags": [], "hard_fail": False}, {"model": model, "latency_ms": 1, "ok": True}

    with patch(
        "agentic_capital.adapters.llm.local_finance_runtime._call_finance_stage",
        AsyncMock(side_effect=fake_stage),
    ), patch(
        "agentic_capital.adapters.llm.local_finance_runtime._search_rag",
        AsyncMock(return_value=(
            [{"doc_id": "tool_policy.md", "text": "planner must not request order tools"}],
            {"model": "rag_search", "latency_ms": 1, "ok": True},
        )),
    ):
        result = await local_finance_runtime.run_local_finance_decision_pipeline(
            request_id="req-order-tool",
            user_question="005930 주문 실행까지 계획?",
            agent_state={"deployment_mode": "paper", "live_order_enabled": False, "symbol": "005930"},
            required_safety={"paper_trade_only": True, "no_order_tool_in_shadow": True},
            collect_tool_results=collect_tool_results,
        )

    assert result["ok"] is False
    assert result["record_type"] == "raw_model_failure"
    assert result["record"]["failure_type"] == "order_tool_in_shadow_plan"
    assert result["record"]["retrain_candidate"] is True
    assert result["record"]["details"]["forbidden_tools"] == ["submit_order"]
    assert "submit_order" in result["record"]["planned_tools"]
    assert result["record"]["action"] == "CALL_TOOL"
    assert result["record"]["evidence_ids"] == ["tool_policy.md"]


@pytest.mark.asyncio
async def test_local_finance_decision_pipeline_blocks_trade_without_rag_evidence():
    async def collect_tool_results(payload):
        return {
            "get_balance": {"available": 1_000_000, "currency": "KRW"},
            "get_positions": [],
            "get_quote": {"price": 70_000, "symbol": "005930", "market": "kr_stock"},
            "get_market_session": {"state": "regular", "is_open": True, "regular_session": True},
            "get_risk_limit": {"max_order_value": 1_000_000},
            "search_rag": {
                "evidence_ids": payload["evidence_ids"],
                "evidence_count": len(payload["evidence"]),
            },
        }

    async def fake_stage(*, model, payload, system):
        if model == local_finance_runtime.FINANCE_RAG_QUERY_MODEL:
            return {
                "query": "005930 근거 없이 매수?",
                "queries": ["005930 근거 없이 매수?"],
                "symbol": "005930",
                "market": "kr_stock",
                "route": "rag_and_fresh_quote",
                "requires_fresh_data": True,
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL:
            return {
                "tool_plan": [
                    {"tool": "search_rag"},
                    {"tool": "get_market_session"},
                    {"tool": "get_balance"},
                    {"tool": "get_positions"},
                    {"tool": "get_quote"},
                    {"tool": "get_risk_limit"},
                ],
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_DECISION_MODEL:
            return {
                "action": "BUY",
                "symbol": "005930",
                "market": "kr_stock",
                "quantity": 1,
                "required_tools": [
                    "search_rag",
                    "get_balance",
                    "get_positions",
                    "get_quote",
                    "get_market_session",
                    "get_risk_limit",
                ],
                "evidence_ids": ["fabricated-evidence"],
                "reason": "paper shadow candidate only",
            }, {"model": model, "latency_ms": 1, "ok": True}
        return {"risk_flags": [], "hard_fail": False}, {"model": model, "latency_ms": 1, "ok": True}

    with patch(
        "agentic_capital.adapters.llm.local_finance_runtime._call_finance_stage",
        AsyncMock(side_effect=fake_stage),
    ), patch(
        "agentic_capital.adapters.llm.local_finance_runtime._search_rag",
        AsyncMock(return_value=([], {"model": "rag_search", "latency_ms": 1, "ok": True})),
    ):
        result = await local_finance_runtime.run_local_finance_decision_pipeline(
            request_id="req-missing-rag-evidence",
            user_question="005930 근거 없이 매수?",
            agent_state={"deployment_mode": "paper", "live_order_enabled": False, "symbol": "005930"},
            required_safety={"paper_trade_only": True, "require_evidence_ids": True},
            collect_tool_results=collect_tool_results,
        )

    assert result["ok"] is False
    assert result["record_type"] == "raw_model_failure"
    assert result["record"]["failure_type"] == "trade_missing_rag_evidence"
    assert result["record"]["retrain_candidate"] is True
    assert result["record"]["action"] == "BUY"
    assert result["record"]["evidence_ids"] == ["fabricated-evidence"]
    assert result["evidence_ids"] == []


@pytest.mark.asyncio
async def test_local_finance_decision_pipeline_records_risk_guard_hard_fail_as_raw_failure():
    async def collect_tool_results(payload):
        return {
            "get_balance": {"available": 1_000_000, "currency": "KRW"},
            "get_positions": [],
            "get_quote": {"price": 70_000, "symbol": "005930", "market": "kr_stock"},
            "get_market_session": {"state": "regular", "is_open": True, "regular_session": True},
            "get_risk_limit": {"max_order_value": 1_000_000},
            "search_rag": {
                "evidence_ids": payload["evidence_ids"],
                "evidence_count": len(payload["evidence"]),
            },
        }

    async def fake_stage(*, model, payload, system):
        if model == local_finance_runtime.FINANCE_RAG_QUERY_MODEL:
            return {
                "query": "005930 매수?",
                "queries": ["005930 매수?"],
                "symbol": "005930",
                "market": "kr_stock",
                "route": "rag_and_fresh_quote",
                "requires_fresh_data": True,
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL:
            return {
                "tool_plan": [
                    {"tool": "search_rag"},
                    {"tool": "get_market_session"},
                    {"tool": "get_balance"},
                    {"tool": "get_positions"},
                    {"tool": "get_quote"},
                    {"tool": "get_risk_limit"},
                ],
                "forbidden_tools": ["submit_order"],
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_DECISION_MODEL:
            return {
                "action": "BUY",
                "symbol": "005930",
                "market": "kr_stock",
                "quantity": 1,
                "required_tools": [
                    "search_rag",
                    "get_balance",
                    "get_positions",
                    "get_quote",
                    "get_market_session",
                    "get_risk_limit",
                ],
                "evidence_ids": ["risk_policy.md"],
                "reason": "수익 보장 후보",
            }, {"model": model, "latency_ms": 1, "ok": True}
        return {
            "risk_flags": ["profit_guarantee"],
            "hard_fail": True,
            "explanation": "profit guarantee is forbidden",
        }, {"model": model, "latency_ms": 1, "ok": True}

    with patch(
        "agentic_capital.adapters.llm.local_finance_runtime._call_finance_stage",
        AsyncMock(side_effect=fake_stage),
    ), patch(
        "agentic_capital.adapters.llm.local_finance_runtime._search_rag",
        AsyncMock(return_value=(
            [{"doc_id": "risk_policy.md", "text": "profit guarantees are forbidden"}],
            {"model": "rag_search", "latency_ms": 1, "ok": True},
        )),
    ):
        result = await local_finance_runtime.run_local_finance_decision_pipeline(
            request_id="req-risk-guard",
            user_question="005930 매수 수익 보장 가능?",
            agent_state={"deployment_mode": "paper", "live_order_enabled": False, "symbol": "005930"},
            required_safety={"paper_trade_only": True, "no_profit_guarantee": True},
            collect_tool_results=collect_tool_results,
        )

    assert result["ok"] is False
    assert result["record_type"] == "raw_model_failure"
    assert result["record"]["failure_type"] == "risk_guard_hard_fail"
    assert result["record"]["retrain_candidate"] is True
    assert result["record"]["action"] == "BUY"
    assert result["record"]["details"]["risk_flags"] == ["profit_guarantee"]
    assert result["risk_flags"] == ["profit_guarantee"]
    assert result["decision"]["action"] == "BUY"
    assert result["record"]["evidence_ids"] == ["risk_policy.md"]


@pytest.mark.asyncio
async def test_local_finance_decision_pipeline_blocks_buy_when_market_closed():
    async def collect_tool_results(payload):
        return {
            "get_balance": {"available": 1_000_000, "currency": "KRW"},
            "get_positions": [],
            "get_quote": {"price": 70_000, "symbol": "005930", "market": "kr_stock"},
            "get_market_session": {"state": "closed", "is_open": False, "regular_session": False},
            "get_risk_limit": {"max_order_value": 1_000_000},
            "search_rag": {
                "evidence_ids": payload["evidence_ids"],
                "evidence_count": len(payload["evidence"]),
            },
        }

    async def fake_stage(*, model, payload, system):
        if model == local_finance_runtime.FINANCE_RAG_QUERY_MODEL:
            return {
                "query": "005930 장 마감 매수?",
                "queries": ["005930 장 마감 매수?"],
                "symbol": "005930",
                "market": "kr_stock",
                "route": "rag_and_fresh_quote",
                "requires_fresh_data": True,
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL:
            return {
                "tool_plan": [
                    {"tool": "search_rag"},
                    {"tool": "get_market_session"},
                    {"tool": "get_balance"},
                    {"tool": "get_positions"},
                    {"tool": "get_quote"},
                    {"tool": "get_risk_limit"},
                ],
                "forbidden_tools": ["submit_order"],
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_DECISION_MODEL:
            return {
                "action": "BUY",
                "symbol": "005930",
                "market": "kr_stock",
                "quantity": 1,
                "required_tools": [
                    "search_rag",
                    "get_balance",
                    "get_positions",
                    "get_quote",
                    "get_market_session",
                    "get_risk_limit",
                ],
                "evidence_ids": ["market_session_policy.md"],
                "reason": "paper shadow candidate only",
            }, {"model": model, "latency_ms": 1, "ok": True}
        return {"risk_flags": [], "hard_fail": False}, {"model": model, "latency_ms": 1, "ok": True}

    with patch(
        "agentic_capital.adapters.llm.local_finance_runtime._call_finance_stage",
        AsyncMock(side_effect=fake_stage),
    ), patch(
        "agentic_capital.adapters.llm.local_finance_runtime._search_rag",
        AsyncMock(return_value=(
            [{"doc_id": "market_session_policy.md", "text": "regular session required before trade"}],
            {"model": "rag_search", "latency_ms": 1, "ok": True},
        )),
    ):
        result = await local_finance_runtime.run_local_finance_decision_pipeline(
            request_id="req-market-closed",
            user_question="005930 장 마감인데 매수?",
            agent_state={"deployment_mode": "paper", "live_order_enabled": False, "symbol": "005930"},
            required_safety={"paper_trade_only": True, "regular_session_required": True},
            collect_tool_results=collect_tool_results,
        )

    assert result["ok"] is False
    assert result["record_type"] == "raw_model_failure"
    assert result["record"]["failure_type"] == "trade_when_market_closed"
    assert result["record"]["retrain_candidate"] is True
    assert result["record"]["action"] == "BUY"
    assert result["record"]["evidence_ids"] == ["market_session_policy.md"]


@pytest.mark.asyncio
async def test_local_finance_decision_pipeline_blocks_buy_with_unknown_market_session():
    async def collect_tool_results(payload):
        return {
            "get_balance": {"available": 1_000_000, "currency": "KRW"},
            "get_positions": [],
            "get_quote": {"price": 70_000, "symbol": "005930", "market": "kr_stock"},
            "get_market_session": {},
            "get_risk_limit": {"max_order_value": 1_000_000},
            "search_rag": {
                "evidence_ids": payload["evidence_ids"],
                "evidence_count": len(payload["evidence"]),
            },
        }

    async def fake_stage(*, model, payload, system):
        if model == local_finance_runtime.FINANCE_RAG_QUERY_MODEL:
            return {
                "query": "005930 장 상태 미확인 매수?",
                "queries": ["005930 장 상태 미확인 매수?"],
                "symbol": "005930",
                "market": "kr_stock",
                "route": "rag_and_fresh_quote",
                "requires_fresh_data": True,
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL:
            return {
                "tool_plan": [
                    {"tool": "search_rag"},
                    {"tool": "get_market_session"},
                    {"tool": "get_balance"},
                    {"tool": "get_positions"},
                    {"tool": "get_quote"},
                    {"tool": "get_risk_limit"},
                ]
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_DECISION_MODEL:
            return {
                "action": "BUY",
                "symbol": "005930",
                "market": "kr_stock",
                "quantity": 1,
                "required_tools": [
                    "search_rag",
                    "get_balance",
                    "get_positions",
                    "get_quote",
                    "get_market_session",
                    "get_risk_limit",
                ],
                "evidence_ids": ["market_session_policy.md"],
                "reason": "paper shadow candidate only",
            }, {"model": model, "latency_ms": 1, "ok": True}
        return {"risk_flags": [], "hard_fail": False}, {"model": model, "latency_ms": 1, "ok": True}

    with patch(
        "agentic_capital.adapters.llm.local_finance_runtime._call_finance_stage",
        AsyncMock(side_effect=fake_stage),
    ), patch(
        "agentic_capital.adapters.llm.local_finance_runtime._search_rag",
        AsyncMock(return_value=(
            [{"doc_id": "market_session_policy.md", "text": "regular session must be explicitly confirmed"}],
            {"model": "rag_search", "latency_ms": 1, "ok": True},
        )),
    ):
        result = await local_finance_runtime.run_local_finance_decision_pipeline(
            request_id="req-market-unknown",
            user_question="005930 장 상태 미확인인데 매수?",
            agent_state={"deployment_mode": "paper", "live_order_enabled": False, "symbol": "005930"},
            required_safety={"paper_trade_only": True, "regular_session_required": True},
            collect_tool_results=collect_tool_results,
        )

    assert result["ok"] is False
    assert result["record_type"] == "raw_model_failure"
    assert result["record"]["failure_type"] == "trade_when_market_closed"
    assert result["record"]["retrain_candidate"] is True
    assert result["record"]["action"] == "BUY"
    assert result["record"]["evidence_ids"] == ["market_session_policy.md"]


@pytest.mark.asyncio
async def test_local_finance_decision_pipeline_blocks_buy_with_conflicting_market_session():
    async def collect_tool_results(payload):
        return {
            "get_balance": {"available": 1_000_000, "currency": "KRW"},
            "get_positions": [],
            "get_quote": {"price": 70_000, "symbol": "005930", "market": "kr_stock"},
            "get_market_session": {"state": "closed", "is_open": True, "regular_session": True},
            "get_risk_limit": {"max_order_value": 1_000_000},
            "search_rag": {
                "evidence_ids": payload["evidence_ids"],
                "evidence_count": len(payload["evidence"]),
            },
        }

    async def fake_stage(*, model, payload, system):
        if model == local_finance_runtime.FINANCE_RAG_QUERY_MODEL:
            return {
                "query": "005930 장 상태 충돌 매수?",
                "queries": ["005930 장 상태 충돌 매수?"],
                "symbol": "005930",
                "market": "kr_stock",
                "route": "rag_and_fresh_quote",
                "requires_fresh_data": True,
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL:
            return {
                "tool_plan": [
                    {"tool": "search_rag"},
                    {"tool": "get_market_session"},
                    {"tool": "get_balance"},
                    {"tool": "get_positions"},
                    {"tool": "get_quote"},
                    {"tool": "get_risk_limit"},
                ]
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_DECISION_MODEL:
            return {
                "action": "BUY",
                "symbol": "005930",
                "market": "kr_stock",
                "quantity": 1,
                "required_tools": [
                    "search_rag",
                    "get_balance",
                    "get_positions",
                    "get_quote",
                    "get_market_session",
                    "get_risk_limit",
                ],
                "evidence_ids": ["market_session_policy.md"],
                "reason": "paper shadow candidate only",
            }, {"model": model, "latency_ms": 1, "ok": True}
        return {"risk_flags": [], "hard_fail": False}, {"model": model, "latency_ms": 1, "ok": True}

    with patch(
        "agentic_capital.adapters.llm.local_finance_runtime._call_finance_stage",
        AsyncMock(side_effect=fake_stage),
    ), patch(
        "agentic_capital.adapters.llm.local_finance_runtime._search_rag",
        AsyncMock(return_value=(
            [{"doc_id": "market_session_policy.md", "text": "closed session state overrides open flags"}],
            {"model": "rag_search", "latency_ms": 1, "ok": True},
        )),
    ):
        result = await local_finance_runtime.run_local_finance_decision_pipeline(
            request_id="req-market-conflict",
            user_question="005930 장 상태가 충돌하면 매수?",
            agent_state={"deployment_mode": "paper", "live_order_enabled": False, "symbol": "005930"},
            required_safety={"paper_trade_only": True, "regular_session_required": True},
            collect_tool_results=collect_tool_results,
        )

    assert result["ok"] is False
    assert result["record_type"] == "raw_model_failure"
    assert result["record"]["failure_type"] == "trade_when_market_closed"
    assert result["record"]["retrain_candidate"] is True
    assert result["record"]["action"] == "BUY"
    assert result["record"]["evidence_ids"] == ["market_session_policy.md"]


@pytest.mark.asyncio
async def test_local_finance_decision_pipeline_blocks_sell_over_position():
    async def collect_tool_results(payload):
        return {
            "get_balance": {"available": 1_000_000, "currency": "KRW"},
            "get_positions": [
                {"symbol": "005930", "market": "kr_stock", "quantity": 1, "current_price": 70_000},
            ],
            "get_quote": {"price": 70_000, "symbol": "005930", "market": "kr_stock"},
            "get_market_session": {"state": "regular", "is_open": True, "regular_session": True},
            "get_risk_limit": {"max_order_value": 1_000_000},
            "search_rag": {
                "evidence_ids": payload["evidence_ids"],
                "evidence_count": len(payload["evidence"]),
            },
        }

    async def fake_stage(*, model, payload, system):
        if model == local_finance_runtime.FINANCE_RAG_QUERY_MODEL:
            return {
                "query": "005930 보유보다 많이 매도?",
                "queries": ["005930 보유보다 많이 매도?"],
                "symbol": "005930",
                "market": "kr_stock",
                "route": "rag_and_fresh_quote",
                "requires_fresh_data": True,
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL:
            return {
                "tool_plan": [
                    {"tool": "search_rag"},
                    {"tool": "get_market_session"},
                    {"tool": "get_balance"},
                    {"tool": "get_positions"},
                    {"tool": "get_quote"},
                    {"tool": "get_risk_limit"},
                ],
                "forbidden_tools": ["submit_order"],
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_DECISION_MODEL:
            return {
                "action": "SELL",
                "symbol": "005930",
                "market": "kr_stock",
                "quantity": 3,
                "required_tools": [
                    "search_rag",
                    "get_balance",
                    "get_positions",
                    "get_quote",
                    "get_market_session",
                    "get_risk_limit",
                ],
                "evidence_ids": ["position_policy.md"],
                "reason": "paper shadow candidate only",
            }, {"model": model, "latency_ms": 1, "ok": True}
        return {"risk_flags": [], "hard_fail": False}, {"model": model, "latency_ms": 1, "ok": True}

    with patch(
        "agentic_capital.adapters.llm.local_finance_runtime._call_finance_stage",
        AsyncMock(side_effect=fake_stage),
    ), patch(
        "agentic_capital.adapters.llm.local_finance_runtime._search_rag",
        AsyncMock(return_value=(
            [{"doc_id": "position_policy.md", "text": "sell quantity must not exceed held quantity"}],
            {"model": "rag_search", "latency_ms": 1, "ok": True},
        )),
    ):
        result = await local_finance_runtime.run_local_finance_decision_pipeline(
            request_id="req-sell-position",
            user_question="005930 보유보다 많이 매도?",
            agent_state={"deployment_mode": "paper", "live_order_enabled": False, "symbol": "005930"},
            required_safety={"paper_trade_only": True, "owned_position_required": True},
            collect_tool_results=collect_tool_results,
        )

    assert result["ok"] is False
    assert result["record_type"] == "raw_model_failure"
    assert result["record"]["failure_type"] == "trade_exceeds_position"
    assert result["record"]["retrain_candidate"] is True
    assert result["record"]["details"]["owned_quantity"] == 1
    assert result["record"]["details"]["requested_quantity"] == 3
    assert result["record"]["action"] == "SELL"
    assert result["record"]["evidence_ids"] == ["position_policy.md"]


@pytest.mark.asyncio
async def test_call_finance_stage_parses_structured_gateway_repair_payload():
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({
                                "action": "CALL_TOOL",
                                "symbol": "005930",
                                "required_tools": ["get_quote"],
                                "evidence_ids": ["source_reference.md"],
                            })
                        }
                    }
                ]
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            self.requests = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, *args, **kwargs):
            self.requests.append((args, kwargs))
            return _Response()

    with patch("agentic_capital.adapters.llm.local_finance_runtime.httpx.AsyncClient", _Client), \
         patch.object(local_finance_runtime.settings, "local_llm_base_url", "http://127.0.0.1:8080/v1"), \
         patch.object(local_finance_runtime.settings, "local_llm_api_key", ""):
        payload, meta = await local_finance_runtime._call_finance_stage(
            model=local_finance_runtime.FINANCE_DECISION_MODEL,
            payload={"user_question": "005930 지금 매수?"},
            system="Return JSON.",
        )

    assert payload["action"] == "CALL_TOOL"
    assert payload["symbol"] == "005930"
    assert payload["evidence_ids"] == ["source_reference.md"]
    assert meta["model"] == local_finance_runtime.FINANCE_DECISION_MODEL


@pytest.mark.asyncio
async def test_local_finance_pipeline_records_call_tool_shadow_from_gateway_repair():
    async def collect_tool_results(payload):
        return {
            "search_rag": {
                "evidence_ids": payload["evidence_ids"],
                "evidence_count": len(payload["evidence"]),
            }
        }

    async def fake_stage(*, model, payload, system):
        if model == local_finance_runtime.FINANCE_RAG_QUERY_MODEL:
            return {
                "query": "005930 지금 매수?",
                "queries": ["005930 지금 매수?"],
                "symbol": "005930",
                "market": "kr_stock",
                "route": "rag_and_fresh_quote",
                "requires_fresh_data": True,
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_TOOL_PLANNER_MODEL:
            return {
                "tool_plan": [
                    {"tool": "search_rag"},
                    {"tool": "get_market_session"},
                    {"tool": "get_balance"},
                    {"tool": "get_positions"},
                    {"tool": "get_quote"},
                    {"tool": "get_risk_limit"},
                ],
                "forbidden_tools": ["submit_order"],
            }, {"model": model, "latency_ms": 1, "ok": True}
        if model == local_finance_runtime.FINANCE_DECISION_MODEL:
            return {
                "action": "CALL_TOOL",
                "symbol": "005930",
                "market": "kr_stock",
                "required_tools": [
                    "search_rag",
                    "get_balance",
                    "get_positions",
                    "get_quote",
                    "get_market_session",
                    "get_risk_limit",
                ],
                "evidence_ids": ["source_reference.md"],
                "risk_tags": ["missing_tool_results", "paper_shadow_only"],
            }, {"model": model, "latency_ms": 1, "ok": True}
        return {"risk_flags": ["missing_tool_results"], "hard_fail": False}, {"model": model, "latency_ms": 1, "ok": True}

    with patch(
        "agentic_capital.adapters.llm.local_finance_runtime._call_finance_stage",
        AsyncMock(side_effect=fake_stage),
    ), patch(
        "agentic_capital.adapters.llm.local_finance_runtime._search_rag",
        AsyncMock(return_value=(
            [{"doc_id": "source_reference.md", "text": "decision contract"}],
            {"model": "rag_search", "latency_ms": 1, "ok": True},
        )),
    ):
        result = await local_finance_runtime.run_local_finance_decision_pipeline(
            request_id="req-2",
            user_question="005930 지금 매수?",
            agent_state={"deployment_mode": "paper", "live_order_enabled": False, "symbol": "005930"},
            required_safety={"paper_trade_only": True},
            collect_tool_results=collect_tool_results,
        )

    assert result["record_type"] == "finance_paper_shadow_decision"
    assert result["record"]["action"] == "CALL_TOOL"
    assert result["record"]["would_submit_order"] is False
    assert "get_quote" in result["record"]["missing_tool_results"]
