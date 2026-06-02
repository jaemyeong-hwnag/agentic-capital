"""Readiness and smoke checks for the local finance LLM sidecar."""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from agentic_capital.adapters.llm.local_finance_shadow import (
    FinanceShadowValidationError,
    build_finance_shadow_failure_record,
    build_finance_shadow_record,
    validate_finance_shadow_payload,
)
from agentic_capital.adapters.llm.local_psychology_runtime import (
    LocalPsychologyRuntimeError,
    build_finance_soft_context,
)
from agentic_capital.config import settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = structlog.get_logger()

SAFE_NO_CONTEXT_ACTIONS = {"CALL_TOOL", "WAIT", "REJECT", "NO_CONTEXT", "OBSERVE", "HOLD"}
TRADE_ACTIONS = {"BUY", "SELL"}
FINANCE_RAG_QUERY_MODEL = "finance_rag_query_model"
FINANCE_TOOL_PLANNER_MODEL = "finance_tool_planner_model"
FINANCE_DECISION_MODEL = "finance_decision_model"
FINANCE_RISK_GUARD_MODEL = "finance_risk_guard_model"
REQUIRED_FINANCE_TOOL_RESULT_IDS = (
    "get_balance",
    "get_positions",
    "get_quote",
    "get_market_session",
    "get_risk_limit",
    "search_rag",
)
FINANCE_STAGE_BASE_URL_SETTINGS = {
    FINANCE_RAG_QUERY_MODEL: "local_finance_rag_query_base_url",
    FINANCE_TOOL_PLANNER_MODEL: "local_finance_tool_planner_base_url",
    FINANCE_DECISION_MODEL: "local_finance_decision_base_url",
    FINANCE_RISK_GUARD_MODEL: "local_finance_risk_guard_base_url",
}


class LocalFinanceRuntimeError(RuntimeError):
    """Raised when the configured local finance LLM runtime is not usable."""


class LocalFinanceStageError(LocalFinanceRuntimeError):
    """Raised when a specific finance sidecar stage call fails."""

    def __init__(
        self,
        stage: str,
        message: str,
        *,
        status_code: int | None = None,
        body_summary: str = "",
        latency_ms: int = 0,
        compact_payload_hash: str = "",
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.status_code = status_code
        self.body_summary = body_summary
        self.latency_ms = latency_ms
        self.compact_payload_hash = compact_payload_hash

    def to_meta(self) -> dict[str, Any]:
        return {
            "model": self.stage,
            "stage": self.stage,
            "latency_ms": self.latency_ms,
            "ok": False,
            "status_code": self.status_code,
            "compact_payload_hash": self.compact_payload_hash,
            "failure_body_summary": self.body_summary,
            "error": type(self).__name__,
        }


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _gateway_root(base_url: str) -> str:
    root = base_url.rstrip("/")
    return root[:-3] if root.endswith("/v1") else root


def _expected_model() -> str:
    return settings.local_llm_expected_health_model.strip() or settings.local_llm_model.strip()


def _extract_health_model(payload: dict[str, Any]) -> str:
    for key in ("model", "llm_model", "service", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = payload.get("config")
    if isinstance(nested, dict):
        return _extract_health_model(nested)
    return ""


def _validate_health_payload(payload: dict[str, Any], expected_model: str) -> str:
    actual_model = _extract_health_model(payload)
    if not actual_model:
        raise LocalFinanceRuntimeError("local_llm_health_missing_model")

    actual_lower = actual_model.lower()
    expected_lower = expected_model.lower()
    if expected_lower.startswith("finance_") and ("psychology" in actual_lower or "health" in actual_lower):
        raise LocalFinanceRuntimeError(
            f"local_llm_model_category_mismatch: expected={expected_model} actual={actual_model}"
        )
    if actual_model != expected_model:
        raise LocalFinanceRuntimeError(f"local_llm_model_mismatch: expected={expected_model} actual={actual_model}")

    llama_reachable = payload.get("llama_reachable")
    if llama_reachable is False:
        raise LocalFinanceRuntimeError("local_llm_llama_unreachable")
    ok_value = payload.get("ok")
    if ok_value is False:
        raise LocalFinanceRuntimeError("local_llm_health_not_ok")

    return actual_model


def _check_finance_health(*, base_url: str, expected_model: str) -> dict[str, Any]:
    health_url = _join_url(_gateway_root(base_url), "/healthz")
    try:
        response = httpx.get(health_url, timeout=settings.local_llm_health_timeout_seconds)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise LocalFinanceRuntimeError(f"local_llm_health_unavailable: {health_url}") from exc
    if not isinstance(payload, dict):
        raise LocalFinanceRuntimeError("local_llm_health_invalid_payload")

    actual_model = _validate_health_payload(payload, expected_model)
    return {
        "health_url": health_url,
        "expected_model": expected_model,
        "actual_model": actual_model,
        "ok": True,
    }


def check_local_finance_health() -> dict[str, Any]:
    """Check `/healthz` and verify that it is the expected finance service."""
    return _check_finance_health(base_url=settings.local_llm_base_url, expected_model=_expected_model())


def _configured_stage_base_urls() -> dict[str, str]:
    configured: dict[str, str] = {}
    for model, setting_name in FINANCE_STAGE_BASE_URL_SETTINGS.items():
        base_url = str(getattr(settings, setting_name, "") or "").strip()
        if base_url:
            configured[model] = base_url
    return configured


def check_local_finance_pipeline_health() -> dict[str, Any]:
    """Check explicitly configured finance stage sidecars before paper trading."""
    stages = {
        model: _check_finance_health(base_url=base_url, expected_model=model)
        for model, base_url in _configured_stage_base_urls().items()
    }
    return {"ok": True, "checked": len(stages), "stages": stages}


def _auth_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.local_llm_api_key:
        headers["Authorization"] = f"Bearer {settings.local_llm_api_key}"
    return headers


def _extract_content(payload: dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"].get("content", "")
    except (KeyError, IndexError, TypeError) as exc:
        raise LocalFinanceRuntimeError("local_finance_smoke_missing_content") from exc
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = "\n".join(line for line in stripped.splitlines() if not line.strip().startswith("```")).strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(stripped[start:end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_action(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().upper()


def validate_finance_decision_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a local finance decision response before paper trading starts."""
    psychology_context = payload.get("psychology_context")
    if isinstance(psychology_context, dict):
        try:
            payload = {**payload, "psychology_context": build_finance_soft_context(psychology_context)}
        except LocalPsychologyRuntimeError as exc:
            raise LocalFinanceRuntimeError(f"local_finance_psychology_context_unsafe: {exc}") from exc

    action = _normalize_action(payload.get("action") or payload.get("decision") or payload.get("status"))
    if not action:
        reason = str(payload.get("reason") or payload.get("message") or "").lower()
        if "no_context" in reason or "근거 부족" in reason:
            action = "NO_CONTEXT"
    if not action:
        raise LocalFinanceRuntimeError("local_finance_smoke_missing_action")

    evidence_ids = payload.get("evidence_ids") or []
    required_tools = payload.get("required_tools") or payload.get("tool_results") or []
    if action in TRADE_ACTIONS and (not evidence_ids or not required_tools):
        raise LocalFinanceRuntimeError(f"local_finance_smoke_unsafe_trade_action: action={action}")
    if action not in SAFE_NO_CONTEXT_ACTIONS and action not in TRADE_ACTIONS:
        raise LocalFinanceRuntimeError(f"local_finance_smoke_unknown_action: action={action}")
    try:
        validate_finance_shadow_payload(payload)
    except FinanceShadowValidationError as exc:
        if action in TRADE_ACTIONS:
            raise LocalFinanceRuntimeError(
                f"local_finance_smoke_unsafe_trade_action: action={action} reason={exc.code}"
            ) from exc
        if action == "CALL_TOOL" and exc.code == "call_tool_missing_required_tools":
            return {
                "action": action,
                "evidence_count": len(evidence_ids) if isinstance(evidence_ids, list) else 0,
                "required_tools_count": len(required_tools) if isinstance(required_tools, list) else 0,
                "shadow_warning": exc.code,
            }
        raise LocalFinanceRuntimeError(f"local_finance_smoke_shadow_guard_failed: {exc.code}") from exc
    return {
        "action": action,
        "evidence_count": len(evidence_ids) if isinstance(evidence_ids, list) else 0,
        "required_tools_count": len(required_tools) if isinstance(required_tools, list) else 0,
    }


def _base_url_for_model(model: str) -> str:
    specific_setting = FINANCE_STAGE_BASE_URL_SETTINGS.get(model, "")
    specific = str(getattr(settings, specific_setting, "") or "").strip() if specific_setting else ""
    return specific or settings.local_llm_base_url


def _chat_url(model: str = "") -> str:
    return _join_url(_base_url_for_model(model), "/chat/completions")


def _coerce_json_payload(content: str, *, fallback_action: str = "NO_CONTEXT") -> dict[str, Any]:
    parsed = _extract_json_object(content)
    if parsed is not None:
        return parsed
    lowered = content.lower()
    if "no_context" in lowered or "근거 부족" in lowered:
        return {"action": fallback_action, "reason": content[:500]}
    return {"action": fallback_action, "reason": content[:500], "parse_error": "invalid_json"}


def _summary_text(value: Any, *, limit: int = 500) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else f"{compact[:limit].rstrip()}..."


def _payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _stage_failure_meta(stage: str, exc: Exception) -> dict[str, Any]:
    if isinstance(exc, LocalFinanceStageError):
        return exc.to_meta()
    return {
        "model": stage,
        "stage": stage,
        "latency_ms": 0,
        "ok": False,
        "status_code": None,
        "compact_payload_hash": "",
        "failure_body_summary": _summary_text(str(exc)),
        "error": type(exc).__name__,
    }


async def _call_finance_stage(
    *,
    model: str,
    payload: dict[str, Any],
    system: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call one local finance model stage through the OpenAI-compatible gateway."""
    started = time.perf_counter()
    compact_payload_hash = _payload_hash(payload)
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)},
        ],
        "temperature": 0.0,
    }
    response: httpx.Response | None = None
    try:
        async with httpx.AsyncClient(timeout=settings.local_llm_timeout_seconds) as client:
            response = await client.post(_chat_url(model), headers=_auth_headers(), json=request_payload)
            status_code = int(getattr(response, "status_code", 200) or 200)
            if status_code >= 400:
                raise LocalFinanceStageError(
                    model,
                    f"local_finance_stage_http_error:{model}:{status_code}",
                    status_code=status_code,
                    body_summary=_summary_text(response.text),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    compact_payload_hash=compact_payload_hash,
                )
            content = _extract_content(response.json())
    except LocalFinanceStageError:
        raise
    except Exception as exc:
        raise LocalFinanceStageError(
            model,
            f"local_finance_stage_call_failed:{model}:{type(exc).__name__}",
            status_code=getattr(response, "status_code", None),
            body_summary=_summary_text(getattr(response, "text", "") or str(exc)),
            latency_ms=int((time.perf_counter() - started) * 1000),
            compact_payload_hash=compact_payload_hash,
        ) from exc
    latency_ms = int((time.perf_counter() - started) * 1000)
    parsed = _coerce_json_payload(content)
    return parsed, {
        "model": model,
        "stage": model,
        "latency_ms": latency_ms,
        "ok": True,
        "status_code": getattr(response, "status_code", None),
        "compact_payload_hash": compact_payload_hash,
    }


def _extract_queries(rag_query_payload: dict[str, Any], fallback_query: str) -> list[str]:
    value = rag_query_payload.get("queries") or rag_query_payload.get("query")
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        queries = [str(item).strip() for item in value if str(item).strip()]
        if queries:
            return queries
    return [fallback_query]


def _extract_evidence_ids(evidence: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for idx, item in enumerate(evidence):
        if not isinstance(item, dict):
            continue
        evidence_id = item.get("id") or item.get("evidence_id") or item.get("doc_id") or item.get("chunk_id")
        ids.append(str(evidence_id or f"rag-{idx}"))
    return ids


def _compact_evidence_payload(evidence: list[dict[str, Any]], *, limit: int = 6) -> list[dict[str, Any]]:
    """Build compact evidence for planning without sending full document text."""
    compact: list[dict[str, Any]] = []
    for idx, item in enumerate(evidence[:limit]):
        if not isinstance(item, dict):
            continue
        evidence_id = item.get("id") or item.get("evidence_id") or item.get("doc_id") or item.get("chunk_id")
        text = item.get("summary") or item.get("title") or item.get("text") or item.get("content") or ""
        compact.append({
            "id": str(evidence_id or f"rag-{idx}"),
            "source": str(item.get("source") or item.get("path") or item.get("doc") or ""),
            "score": item.get("score"),
            "preview": _summary_text(text, limit=180),
        })
    return compact


def _compact_finance_tool_results(tool_results: dict[str, Any]) -> dict[str, Any]:
    """Build the decision/risk sidecar view without bulky raw evidence."""
    allowed = {
        "get_balance",
        "get_positions",
        "get_quote",
        "get_market_session",
        "get_risk_limit",
        "search_rag",
        "finance_decision_payload",
        "_errors",
        "_meta",
    }
    compact = {name: value for name, value in tool_results.items() if name in allowed}
    rag = compact.get("search_rag")
    if isinstance(rag, dict):
        evidence = rag.get("evidence")
        compact["search_rag"] = {
            **rag,
            "evidence": _compact_evidence_payload(evidence if isinstance(evidence, list) else []),
        }
    finance_context = compact.get("finance_decision_payload")
    if isinstance(finance_context, dict):
        context = dict(finance_context)
        context_rag = context.get("rag")
        if isinstance(context_rag, dict):
            evidence = context_rag.get("evidence")
            context["rag"] = {
                **context_rag,
                "evidence": _compact_evidence_payload(evidence if isinstance(evidence, list) else []),
            }
        context.pop("tool_results", None)
        compact["finance_decision_payload"] = context
    return compact


def _compact_agent_state(agent_state: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "deployment_mode",
        "live_order_enabled",
        "agent_name",
        "symbol",
        "symbols",
        "market",
        "open_markets",
        "capital_limit",
        "risk_per_trade_pct",
    }
    return {key: agent_state.get(key) for key in allowed if key in agent_state}


def _compact_rag_query_payload(rag_query: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in ("query", "route", "requires_fresh_data", "no_context_if_empty", "symbol", "market"):
        if key in rag_query:
            value = rag_query[key]
            compact[key] = _summary_text(value, limit=160) if isinstance(value, str) else value
    queries = rag_query.get("queries")
    if isinstance(queries, list):
        compact["queries"] = [_summary_text(query, limit=120) for query in queries[:3]]
    return compact


def _paper_runtime_context(
    *,
    agent_state: dict[str, Any],
    required_safety: dict[str, Any],
) -> dict[str, Any]:
    """Expose explicit paper-mode metadata for finance gateway repairs."""
    deployment_mode = str(agent_state.get("deployment_mode") or "").strip().lower()
    trading_mode = str(agent_state.get("trading_mode") or "").strip().lower()
    live_order_enabled = bool(agent_state.get("live_order_enabled"))
    paper_trade_only = bool(required_safety.get("paper_trade_only"))
    kis_is_paper = bool(required_safety.get("kis_is_paper", settings.kis_is_paper))
    futures_live_orders_enabled = bool(
        required_safety.get("futures_live_orders_enabled", settings.futures_live_orders_enabled)
    )
    paper_mode = paper_trade_only or kis_is_paper or deployment_mode in {"paper", "shadow"} or trading_mode == "paper"
    account_mode = "paper" if paper_mode else "live"
    return {
        "account_mode": account_mode,
        "deployment_mode": "paper" if paper_mode else (deployment_mode or account_mode),
        "trading_mode": "paper" if paper_mode else (trading_mode or account_mode),
        "paper_trading_mode": paper_mode,
        "live_order_permission": live_order_enabled and not futures_live_orders_enabled and not paper_mode,
    }


def _compact_tool_plan_payload(tool_plan: dict[str, Any]) -> dict[str, Any]:
    plan = tool_plan.get("tool_plan") or tool_plan.get("tools") or tool_plan.get("tool_calls") or []
    compact_plan: list[dict[str, Any]] = []
    if isinstance(plan, list):
        for item in plan[:8]:
            if isinstance(item, str):
                compact_plan.append({"tool": item})
            elif isinstance(item, dict):
                args = item.get("args") if isinstance(item.get("args"), dict) else {}
                compact_plan.append({
                    "tool": str(item.get("tool") or item.get("name") or item.get("function") or ""),
                    "args": {
                        str(key): _summary_text(value, limit=80) if isinstance(value, str) else value
                        for key, value in args.items()
                    },
                })
    return {
        "tool_plan": [item for item in compact_plan if item.get("tool")],
        "stop_if_missing": tool_plan.get("stop_if_missing", []),
        "fallback": tool_plan.get("fallback"),
        "paper_trade_only": tool_plan.get("paper_trade_only", True),
    }


def _tool_result_stage_summary(tool_results: dict[str, Any]) -> dict[str, Any]:
    tool_result_ids = _available_tool_result_ids(tool_results)
    return {
        "available": tool_result_ids,
        "tool_result_ids": tool_result_ids,
        "errors": tool_results.get("_errors", []),
        "meta": tool_results.get("_meta", {}),
    }


def _compact_decision_for_risk_guard(decision: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in (
        "action",
        "symbol",
        "market",
        "side",
        "quantity",
        "price",
        "confidence",
        "evidence_ids",
        "tool_result_ids",
        "required_tools",
        "risk_tags",
        "no_trade_reason",
    ):
        if key in decision:
            compact[key] = decision[key]
    reason = decision.get("reason") or decision.get("rationale") or decision.get("message")
    if reason:
        compact["reason"] = _summary_text(reason, limit=180)
    return compact


def _risk_guard_finance_context(finance_context: dict[str, Any]) -> dict[str, Any]:
    rag = finance_context.get("rag")
    compact_rag: dict[str, Any] = {}
    if isinstance(rag, dict):
        compact_rag = {
            "evidence_ids": rag.get("evidence_ids", []),
            "evidence_count": rag.get("evidence_count", 0),
        }
    return {
        "balance": finance_context.get("balance", {}),
        "positions": finance_context.get("positions", []),
        "quote": finance_context.get("quote", {}),
        "ohlcv": finance_context.get("ohlcv", {}),
        "market_signal": finance_context.get("market_signal", {}),
        "market_session": finance_context.get("market_session", {}),
        "risk_limit": finance_context.get("risk_limit", {}),
        "rag": compact_rag,
        "tool_result_ids": finance_context.get("tool_result_ids", []),
    }


def _available_tool_result_ids(tool_results: dict[str, Any]) -> list[str]:
    """Return model-facing ids for read-only runtime tool evidence."""
    return sorted(
        key
        for key in tool_results
        if not key.startswith("_") and key != "finance_decision_payload"
    )


def _has_complete_runtime_tool_evidence(tool_results: dict[str, Any], evidence_ids: list[str]) -> bool:
    errors = tool_results.get("_errors")
    return (
        not errors
        and set(REQUIRED_FINANCE_TOOL_RESULT_IDS).issubset(set(_available_tool_result_ids(tool_results)))
    )


def _call_tool_loop_with_sufficient_evidence(
    *,
    decision: dict[str, Any],
    risk_flags: list[str],
    tool_results: dict[str, Any],
    evidence_ids: list[str],
) -> bool:
    """Detect a finance model asking for already-supplied required evidence."""
    action = _normalize_action(decision.get("action"))
    if action != "CALL_TOOL":
        return False
    if not _has_complete_runtime_tool_evidence(tool_results, evidence_ids):
        return False
    if any("missing_evidence" in str(flag) for flag in risk_flags):
        return True
    no_trade_reason = str(decision.get("no_trade_reason") or "")
    if no_trade_reason in {
        "missing_evidence_review",
        "missing_evidence",
        "missing_tool_results",
        "missing_signal",
        "tool_collection_only",
    }:
        return True
    requested_raw = decision.get("required_tools") or decision.get("tools") or []
    if isinstance(requested_raw, str):
        requested = {requested_raw}
    elif isinstance(requested_raw, list):
        requested = {str(item) for item in requested_raw if str(item)}
    else:
        requested = set()
    return bool(requested & set(REQUIRED_FINANCE_TOOL_RESULT_IDS))


def _repair_paper_non_trade_with_runtime_tool_evidence(
    *,
    decision: dict[str, Any],
    tool_results: dict[str, Any],
    evidence_ids: list[str],
) -> dict[str, Any] | None:
    """Downgrade paper-safe non-trade loops when runtime read tools already cover the cycle."""
    original_action = _normalize_action(decision.get("action"))
    if original_action not in {"NO_CONTEXT", "CALL_TOOL"}:
        return None
    if not _has_complete_runtime_tool_evidence(tool_results, evidence_ids):
        return None
    if tool_results.get("_errors"):
        return None

    risk_tags = decision.get("risk_tags")
    if not isinstance(risk_tags, list):
        risk_tags = []
    reason = str(decision.get("reason") or decision.get("message") or "").strip() or "runtime_tool_evidence_complete"
    repair_tags = {"runtime_tool_evidence_complete"}
    if original_action == "NO_CONTEXT":
        repair_tags.add("no_context_repaired_to_observe")
    else:
        repair_tags.add("call_tool_repaired_to_observe")
    return {
        **decision,
        "action": "OBSERVE",
        "reason": f"{reason}; runtime_tool_evidence_complete",
        "risk_tags": sorted({*map(str, risk_tags), *repair_tags}),
        "repair_applied": True,
        "repair_source": "agentic_capital.local_finance_runtime",
        "repaired_from_action": original_action,
    }


def _deterministic_paper_tool_plan(agent_state: dict[str, Any]) -> dict[str, Any]:
    """Fallback tool plan used when the tool planner sidecar is unavailable."""
    symbol = str(agent_state.get("symbol") or "").strip()
    return {
        "tool_plan": [
            {"tool": "search_rag", "args": {"symbol": symbol} if symbol else {}},
            {"tool": "get_market_session"},
            {"tool": "get_balance"},
            {"tool": "get_positions"},
            {"tool": "get_quote", "args": {"symbol": symbol} if symbol else {}},
            {"tool": "get_ohlcv", "args": {"symbol": symbol, "timeframe": "15m", "limit": 8} if symbol else {}},
            {"tool": "get_risk_limit"},
        ],
        "stop_if_missing": [
            "search_rag",
            "get_market_session",
            "get_balance",
            "get_positions",
            "get_quote",
            "get_risk_limit",
        ],
        "fallback": "deterministic_paper_tool_plan",
        "paper_trade_only": True,
    }


async def _search_rag(
    queries: list[str],
    *,
    top_k: int = 6,
    base_url: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Search the finance RAG gateway. Search failure is evidence, not a crash."""
    started = time.perf_counter()
    search_url = _join_url(_gateway_root(base_url or _base_url_for_model(FINANCE_DECISION_MODEL)), "/search")
    evidence: list[dict[str, Any]] = []
    errors: list[str] = []
    status_codes: list[int] = []
    failure_body_summaries: list[str] = []
    async with httpx.AsyncClient(timeout=settings.local_llm_timeout_seconds) as client:
        for query in queries:
            response: httpx.Response | None = None
            try:
                response = await client.post(
                    search_url,
                    headers=_auth_headers(),
                    json={"query": query, "top_k": top_k},
                )
                status_codes.append(response.status_code)
                response.raise_for_status()
                payload = response.json()
                results = payload.get("results") if isinstance(payload, dict) else None
                if isinstance(results, list):
                    evidence.extend(item for item in results if isinstance(item, dict))
                elif isinstance(payload, list):
                    evidence.extend(item for item in payload if isinstance(item, dict))
            except Exception as exc:
                errors.append(type(exc).__name__)
                failure_body_summaries.append(_summary_text(getattr(response, "text", "") or str(exc)))
    return evidence, {
        "model": "rag_search",
        "stage": "rag_search",
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "ok": not errors,
        "errors": errors,
        "status_code": status_codes[-1] if status_codes else None,
        "failure_body_summary": failure_body_summaries[0] if failure_body_summaries else "",
        "compact_payload_hash": _payload_hash({"queries": queries, "top_k": top_k}),
    }


def _risk_flags(risk_guard_payload: dict[str, Any]) -> list[str]:
    flags = risk_guard_payload.get("risk_flags") or risk_guard_payload.get("flags") or []
    if isinstance(flags, str):
        return [flags]
    if isinstance(flags, list):
        return [str(flag) for flag in flags if str(flag)]
    return []


def _blocked_order_tools(tool_results: dict[str, Any]) -> list[str]:
    errors = tool_results.get("_errors")
    if not isinstance(errors, list):
        return []
    blocked: list[str] = []
    for item in errors:
        if not isinstance(item, dict) or item.get("error") != "order_tool_blocked_in_shadow":
            continue
        tools = item.get("tools") or []
        if isinstance(tools, str):
            tools = [tools]
        if isinstance(tools, list):
            blocked.extend(str(tool) for tool in tools if str(tool))
    return sorted(set(blocked))


def _classify_no_trade_reason(
    *,
    decision: dict[str, Any],
    record: dict[str, Any],
    risk_flags: list[str],
    tool_results: dict[str, Any],
    risk_guard: dict[str, Any],
) -> str | None:
    """Explain why a paper-shadow cycle did not become an order candidate."""
    action = _normalize_action(decision.get("action"))
    explicit_no_trade_reason = str(
        decision.get("no_trade_reason") or record.get("no_trade_reason") or ""
    ).strip()
    explicit_non_trade_reasons = {
        "insufficient_edge",
        "market_condition",
        "risk_guard_block",
        "missing_signal",
        "missing_evidence",
        "missing_tool_results",
        "paper_shadow_only",
        "tool_collection_only",
        "model_rejected_trade",
        "no_context",
        "missing_evidence_ids",
        "missing_evidence_review",
    }
    if action in {"BUY", "SELL"} and record.get("record_type") == "finance_paper_shadow_decision":
        return None
    if record.get("record_type") == "raw_model_failure":
        failure_type = str(record.get("failure_type") or "")
        return f"blocked:{failure_type}" if failure_type else "blocked:raw_model_failure"
    errors = tool_results.get("_errors")
    if isinstance(errors, list) and errors:
        first_error = errors[0] if isinstance(errors[0], dict) else {}
        tool = str(first_error.get("tool") or "tool")
        error = str(first_error.get("error") or "error")
        return f"tool_error:{tool}:{error}"
    if risk_guard.get("hard_fail") is True:
        return "risk_guard_block"
    if explicit_no_trade_reason in explicit_non_trade_reasons:
        return explicit_no_trade_reason
    if any("missing_evidence" in str(flag) for flag in risk_flags):
        return "missing_evidence_review"
    if not decision.get("evidence_ids"):
        return "missing_evidence_ids"
    if action == "CALL_TOOL":
        return "tool_collection_only"
    if action in {"WAIT", "HOLD", "OBSERVE"}:
        return "insufficient_edge"
    if action == "REJECT":
        return "model_rejected_trade"
    if action == "NO_CONTEXT":
        return "no_context"
    return "non_trade_action"


def _normalise_decision_payload(
    decision_payload: dict[str, Any],
    *,
    tool_results: dict[str, Any],
    evidence_ids: list[str],
) -> dict[str, Any]:
    action = _normalize_action(
        decision_payload.get("action") or decision_payload.get("decision") or decision_payload.get("status")
    )
    if not action:
        reason = str(decision_payload.get("reason") or decision_payload.get("message") or "").lower()
        action = "NO_CONTEXT" if "no_context" in reason or "근거 부족" in reason else "WAIT"
    payload = {
        **decision_payload,
        "action": action,
        "evidence_ids": decision_payload.get("evidence_ids") or evidence_ids,
        "tool_result_ids": decision_payload.get("tool_result_ids") or _available_tool_result_ids(tool_results),
        "required_tools": decision_payload.get("required_tools")
        or decision_payload.get("tools")
        or list(tool_results.keys()),
        "tool_results": tool_results,
    }
    return payload


async def run_local_finance_decision_pipeline(
    *,
    request_id: str,
    user_question: str,
    agent_state: dict[str, Any],
    required_safety: dict[str, Any],
    collect_tool_results: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    psychology_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the finance sidecar as a staged decision client.

    This keeps the local finance models on their intended contracts:
    query routing, tool planning, read-only tool collection, decision, and risk guard.
    The function returns a paper-shadow record or a raw-model-failure record; it
    never submits orders.
    """
    started = time.perf_counter()
    sidecar_calls: list[dict[str, Any]] = []
    first_failing_stage: str | None = None
    base_payload = {
        "request_id": request_id,
        "user_question": user_question,
        "agent_state": agent_state,
        "required_safety": required_safety,
    }
    if psychology_context:
        try:
            base_payload["psychology_context"] = build_finance_soft_context(psychology_context)
        except LocalPsychologyRuntimeError as exc:
            raise LocalFinanceRuntimeError(f"local_finance_psychology_context_unsafe: {exc}") from exc
    paper_runtime_context = _paper_runtime_context(
        agent_state=agent_state,
        required_safety=required_safety,
    )
    base_payload.update(paper_runtime_context)

    try:
        rag_query, meta = await _call_finance_stage(
            model=FINANCE_RAG_QUERY_MODEL,
            payload=base_payload,
            system="Return only JSON with queries, filters, route, requires_fresh_data, no_context_if_empty.",
        )
        sidecar_calls.append(meta)

        queries = _extract_queries(rag_query, user_question)
        evidence, search_meta = await _search_rag(queries, base_url=_base_url_for_model(FINANCE_DECISION_MODEL))
        sidecar_calls.append(search_meta)
        evidence_ids = _extract_evidence_ids(evidence)
        compact_evidence = _compact_evidence_payload(evidence)

        planner_payload = {
            **base_payload,
            "rag_query": rag_query,
            "evidence": compact_evidence,
            "evidence_compact": compact_evidence,
            "evidence_count": len(evidence),
            "evidence_ids": evidence_ids,
        }
        try:
            tool_plan, meta = await _call_finance_stage(
                model=FINANCE_TOOL_PLANNER_MODEL,
                payload=planner_payload,
                system=(
                    "Return only JSON with tool_plan and stop_if_missing. "
                    "Do not include live order submission tools in paper/shadow mode."
                ),
            )
            sidecar_calls.append(meta)
        except Exception as exc:
            first_failing_stage = first_failing_stage or FINANCE_TOOL_PLANNER_MODEL
            sidecar_calls.append(_stage_failure_meta(FINANCE_TOOL_PLANNER_MODEL, exc))
            tool_plan = _deterministic_paper_tool_plan(agent_state)
            sidecar_calls.append({
                "model": "deterministic_paper_tool_plan",
                "stage": "tool_planner_fallback",
                "latency_ms": 0,
                "ok": True,
                "status_code": None,
                "compact_payload_hash": _payload_hash(planner_payload),
                "fallback_for": FINANCE_TOOL_PLANNER_MODEL,
            })

        tool_results = await collect_tool_results({
            "tool_plan": tool_plan,
            "rag_query": rag_query,
            "evidence": evidence,
            "evidence_ids": evidence_ids,
        })
        if not isinstance(tool_results, dict):
            tool_results = {"_errors": [{"tool": "collector", "error": "invalid_tool_results"}]}
        compact_tool_results = _compact_finance_tool_results(tool_results)
        compact_finance_context = compact_tool_results.get("finance_decision_payload", {})
        tool_result_ids = _available_tool_result_ids(tool_results)
        if isinstance(compact_finance_context, dict):
            compact_finance_context = {
                **compact_finance_context,
                **paper_runtime_context,
                "tool_result_ids": compact_finance_context.get("tool_result_ids") or tool_result_ids,
            }
        compact_base_payload = {
            "request_id": request_id,
            "user_question": _summary_text(user_question, limit=300),
            "agent_state": _compact_agent_state(agent_state),
            "required_safety": required_safety,
            **paper_runtime_context,
        }

        decision_payload = {
            **compact_base_payload,
            "rag_query": _compact_rag_query_payload(rag_query),
            "tool_plan": _compact_tool_plan_payload(tool_plan if isinstance(tool_plan, dict) else {}),
            "tool_results": _tool_result_stage_summary(tool_results),
            "finance_context": compact_finance_context,
            "evidence": compact_evidence[:3],
            "evidence_count": len(evidence),
            "evidence_ids": evidence_ids,
            "tool_result_ids": tool_result_ids,
        }
        decision, meta = await _call_finance_stage(
            model=FINANCE_DECISION_MODEL,
            payload=decision_payload,
            system=(
                "Return only JSON. Output action must be BUY, SELL, HOLD, WAIT, OBSERVE, "
                "REJECT, CALL_TOOL, or NO_CONTEXT. Treat tool_result_ids and finance_context as "
                "runtime evidence. If tool_result_ids cover search_rag, get_market_session, "
                "get_balance, get_positions, get_quote, and get_risk_limit, do not return "
                "CALL_TOOL or missing_evidence_review only because service-document evidence_ids "
                "are sparse; return HOLD or WAIT with no_trade_reason=insufficient_edge unless "
                "a paper BUY/SELL is justified. Use finance_context.market_signal and 15m OHLCV "
                "as runtime evidence for short-window momentum, but never treat a single quote as "
                "an edge. If balance, positions, quote, risk limit, or runtime evidence is "
                "insufficient, do not return BUY or SELL."
            ),
        )
        sidecar_calls.append(meta)
        decision = _normalise_decision_payload(
            decision,
            tool_results=compact_tool_results,
            evidence_ids=evidence_ids,
        )
        decision["required_tools"] = sorted(set(decision.get("required_tools") or []) | set(tool_result_ids))
        blocked_order_tools = _blocked_order_tools(tool_results)

        risk_guard_payload = {
            "request_id": request_id,
            "agent_state": _compact_agent_state(agent_state),
            "required_safety": required_safety,
            "decision": _compact_decision_for_risk_guard(decision),
            "finance_context": _risk_guard_finance_context(
                compact_finance_context if isinstance(compact_finance_context, dict) else {}
            ),
            "tool_results": _tool_result_stage_summary(tool_results),
        }
        risk_guard, meta = await _call_finance_stage(
            model=FINANCE_RISK_GUARD_MODEL,
            payload=risk_guard_payload,
            system=(
                "Return only JSON with risk_flags, hard_fail, explanation. "
                "Hard fail profit guarantees, unsupported latest-market claims, or live orders without permission."
            ),
        )
        sidecar_calls.append(meta)
        risk_flags = _risk_flags(risk_guard)
        if risk_guard.get("hard_fail") is True:
            decision = {
                **decision,
                "risk_tags": sorted(set([*risk_flags, *decision.get("risk_tags", [])])),
                "reason": f"risk_guard_hard_fail:{risk_guard.get('explanation', '')}",
            }

        repaired_decision = _repair_paper_non_trade_with_runtime_tool_evidence(
            decision=decision,
            tool_results=tool_results,
            evidence_ids=evidence_ids,
        )
        if repaired_decision is not None:
            decision = repaired_decision
            first_failing_stage = first_failing_stage or FINANCE_DECISION_MODEL

        if blocked_order_tools:
            record = build_finance_shadow_failure_record(
                FinanceShadowValidationError(
                    "order_tool_in_shadow_plan",
                    details={"forbidden_tools": blocked_order_tools},
                ),
                {
                    **decision,
                    "tool_plan": tool_plan.get("tool_plan") if isinstance(tool_plan, dict) else tool_plan,
                    "risk_tags": sorted(
                        set(["order_tool_blocked_in_shadow", *risk_flags, *decision.get("risk_tags", [])])
                    ),
                },
                tool_results=tool_results,
            )
        elif risk_guard.get("hard_fail") is True:
            record = build_finance_shadow_failure_record(
                FinanceShadowValidationError(
                    "risk_guard_hard_fail",
                    details={
                        "risk_flags": risk_flags,
                        "explanation": str(risk_guard.get("explanation") or ""),
                    },
                ),
                decision,
                tool_results=tool_results,
            )
        elif _call_tool_loop_with_sufficient_evidence(
            decision=decision,
            risk_flags=risk_flags,
            tool_results=tool_results,
            evidence_ids=evidence_ids,
        ):
            first_failing_stage = first_failing_stage or FINANCE_DECISION_MODEL
            record = build_finance_shadow_failure_record(
                FinanceShadowValidationError(
                    "call_tool_loop_with_sufficient_tool_evidence",
                    details={
                        "risk_flags": risk_flags,
                        "tool_result_ids": _available_tool_result_ids(tool_results),
                        "evidence_ids": evidence_ids,
                    },
                ),
                {
                    **decision,
                    "first_failing_stage": first_failing_stage,
                    "risk_tags": sorted(set(["call_tool_loop", *risk_flags, *decision.get("risk_tags", [])])),
                    "no_trade_reason": "call_tool_loop_with_sufficient_tool_evidence",
                },
                tool_results=tool_results,
            )
        elif _normalize_action(decision.get("action")) == "NO_CONTEXT":
            record = build_finance_shadow_failure_record(
                FinanceShadowValidationError("no_context"),
                decision,
                tool_results=tool_results,
            )
        else:
            try:
                record = build_finance_shadow_record(decision, tool_results=tool_results)
            except FinanceShadowValidationError as exc:
                record = build_finance_shadow_failure_record(exc, decision, tool_results=tool_results)

        no_trade_reason = _classify_no_trade_reason(
            decision=decision,
            record=record,
            risk_flags=risk_flags,
            tool_results=tool_results,
            risk_guard=risk_guard,
        )
        if no_trade_reason:
            decision["no_trade_reason"] = no_trade_reason
            record["no_trade_reason"] = no_trade_reason

        return {
            "ok": record.get("record_type") != "raw_model_failure",
            "request_id": request_id,
            "record": record,
            "record_type": record.get("record_type"),
            "decision": decision,
            "risk_guard": risk_guard,
            "rag_query": rag_query,
            "tool_plan": tool_plan,
            "tool_results": tool_results,
            "evidence": evidence,
            "evidence_ids": evidence_ids,
            "risk_flags": risk_flags,
            "sidecar_calls": sidecar_calls,
            "sidecar_latency_ms": int((time.perf_counter() - started) * 1000),
            "first_failing_stage": first_failing_stage,
        }
    except Exception as exc:
        first_failing_stage = first_failing_stage or getattr(exc, "stage", None) or "finance_sidecar_pipeline"
        if isinstance(exc, LocalFinanceStageError) and not any(
            call.get("stage") == exc.stage and call.get("ok") is False for call in sidecar_calls
        ):
            sidecar_calls.append(exc.to_meta())
        error = FinanceShadowValidationError(
            "sidecar_pipeline_failed",
            details={
                "stage_error": type(exc).__name__,
                "first_failing_stage": first_failing_stage,
            },
        )
        failure_payload = {
            "action": "NO_CONTEXT",
            "symbol": str(agent_state.get("symbol") or ""),
            "market": str(agent_state.get("market") or ""),
            "reason": f"sidecar_pipeline_failed:{type(exc).__name__}",
            "first_failing_stage": first_failing_stage,
        }
        record = build_finance_shadow_failure_record(error, failure_payload, tool_results={})
        logger.warning(
            "local_finance_sidecar_pipeline_failed",
            error=type(exc).__name__,
            first_failing_stage=first_failing_stage,
            sidecar_calls=sidecar_calls,
        )
        return {
            "ok": False,
            "request_id": request_id,
            "record": record,
            "record_type": "raw_model_failure",
            "decision": failure_payload,
            "risk_guard": {},
            "rag_query": {},
            "tool_plan": {},
            "tool_results": {},
            "evidence": [],
            "evidence_ids": [],
            "risk_flags": [],
            "sidecar_calls": sidecar_calls,
            "sidecar_latency_ms": int((time.perf_counter() - started) * 1000),
            "errors": [str(exc)],
            "first_failing_stage": first_failing_stage,
        }


def run_local_finance_smoke() -> dict[str, Any]:
    """Run a safe missing-context smoke query against the local finance gateway."""
    chat_url = _join_url(settings.local_llm_base_url, "/chat/completions")
    request_payload = {
        "model": settings.local_llm_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only JSON. If balance, position, quote, risk limit, or evidence is missing, "
                    "do not return BUY or SELL."
                ),
            },
            {
                "role": "user",
                "content": (
                    "paper-startup-smoke: 005930 지금 매수해도 돼? "
                    "No balance, no position, no quote, no risk limit, no evidence is provided."
                ),
            },
        ],
        "temperature": 0.0,
    }
    try:
        response = httpx.post(
            chat_url,
            headers=_auth_headers(),
            json=request_payload,
            timeout=settings.local_finance_smoke_timeout_seconds,
        )
        response.raise_for_status()
        content = _extract_content(response.json())
    except Exception as exc:
        raise LocalFinanceRuntimeError(f"local_finance_smoke_unavailable: {chat_url}") from exc

    parsed = _extract_json_object(content)
    if parsed is None:
        lowered = content.lower()
        if "no_context" in lowered or "근거 부족" in lowered:
            parsed = {"action": "NO_CONTEXT", "reason": content[:300]}
        else:
            raise LocalFinanceRuntimeError("local_finance_smoke_invalid_json")

    validated = validate_finance_decision_payload(parsed)
    return {
        "chat_url": chat_url,
        "model": settings.local_llm_model,
        **validated,
        "ok": True,
    }


def validate_local_finance_runtime() -> dict[str, Any]:
    """Fail closed unless the local finance runtime is ready for paper trading."""
    if not settings.local_llm_readiness_required:
        return {"ok": True, "skipped": "local_llm_readiness_required_false"}

    health = check_local_finance_health()
    pipeline_health = check_local_finance_pipeline_health()
    smoke = run_local_finance_smoke() if settings.local_finance_smoke_enabled else {"skipped": True}
    logger.info(
        "local_finance_runtime_ready",
        model=health["actual_model"],
        stage_sidecars_checked=pipeline_health["checked"],
        smoke_action=smoke.get("action"),
    )
    return {"ok": True, "health": health, "pipeline_health": pipeline_health, "smoke": smoke}
