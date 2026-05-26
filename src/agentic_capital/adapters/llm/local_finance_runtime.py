"""Readiness and smoke checks for the local finance LLM sidecar."""

from __future__ import annotations

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
FINANCE_STAGE_BASE_URL_SETTINGS = {
    FINANCE_RAG_QUERY_MODEL: "local_finance_rag_query_base_url",
    FINANCE_TOOL_PLANNER_MODEL: "local_finance_tool_planner_base_url",
    FINANCE_DECISION_MODEL: "local_finance_decision_base_url",
    FINANCE_RISK_GUARD_MODEL: "local_finance_risk_guard_base_url",
}


class LocalFinanceRuntimeError(RuntimeError):
    """Raised when the configured local finance LLM runtime is not usable."""


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


async def _call_finance_stage(
    *,
    model: str,
    payload: dict[str, Any],
    system: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call one local finance model stage through the OpenAI-compatible gateway."""
    started = time.perf_counter()
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)},
        ],
        "temperature": 0.0,
    }
    async with httpx.AsyncClient(timeout=settings.local_llm_timeout_seconds) as client:
        response = await client.post(_chat_url(model), headers=_auth_headers(), json=request_payload)
        response.raise_for_status()
        content = _extract_content(response.json())
    latency_ms = int((time.perf_counter() - started) * 1000)
    parsed = _coerce_json_payload(content)
    return parsed, {"model": model, "latency_ms": latency_ms, "ok": True}


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
    async with httpx.AsyncClient(timeout=settings.local_llm_timeout_seconds) as client:
        for query in queries:
            try:
                response = await client.post(
                    search_url,
                    headers=_auth_headers(),
                    json={"query": query, "top_k": top_k},
                )
                response.raise_for_status()
                payload = response.json()
                results = payload.get("results") if isinstance(payload, dict) else None
                if isinstance(results, list):
                    evidence.extend(item for item in results if isinstance(item, dict))
                elif isinstance(payload, list):
                    evidence.extend(item for item in payload if isinstance(item, dict))
            except Exception as exc:
                errors.append(type(exc).__name__)
    return evidence, {
        "model": "rag_search",
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "ok": not errors,
        "errors": errors,
    }


def _risk_flags(risk_guard_payload: dict[str, Any]) -> list[str]:
    flags = risk_guard_payload.get("risk_flags") or risk_guard_payload.get("flags") or []
    if isinstance(flags, str):
        return [flags]
    if isinstance(flags, list):
        return [str(flag) for flag in flags if str(flag)]
    return []


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
) -> dict[str, Any]:
    """Run the finance sidecar as a staged decision client.

    This keeps the local finance models on their intended contracts:
    query routing, tool planning, read-only tool collection, decision, and risk guard.
    The function returns a paper-shadow record or a raw-model-failure record; it
    never submits orders.
    """
    started = time.perf_counter()
    sidecar_calls: list[dict[str, Any]] = []
    base_payload = {
        "request_id": request_id,
        "user_question": user_question,
        "agent_state": agent_state,
        "required_safety": required_safety,
    }

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

        planner_payload = {
            **base_payload,
            "rag_query": rag_query,
            "evidence": evidence,
            "evidence_ids": evidence_ids,
        }
        tool_plan, meta = await _call_finance_stage(
            model=FINANCE_TOOL_PLANNER_MODEL,
            payload=planner_payload,
            system=(
                "Return only JSON with tool_plan and stop_if_missing. "
                "Do not include live order submission tools in paper/shadow mode."
            ),
        )
        sidecar_calls.append(meta)

        tool_results = await collect_tool_results({
            "tool_plan": tool_plan,
            "rag_query": rag_query,
            "evidence": evidence,
            "evidence_ids": evidence_ids,
        })
        if not isinstance(tool_results, dict):
            tool_results = {"_errors": [{"tool": "collector", "error": "invalid_tool_results"}]}

        decision_payload = {
            **base_payload,
            "rag_query": rag_query,
            "tool_plan": tool_plan,
            "tool_results": tool_results,
            "evidence": evidence,
            "evidence_ids": evidence_ids,
        }
        decision, meta = await _call_finance_stage(
            model=FINANCE_DECISION_MODEL,
            payload=decision_payload,
            system=(
                "Return only JSON. Output action must be BUY, SELL, HOLD, WAIT, OBSERVE, "
                "REJECT, CALL_TOOL, or NO_CONTEXT. If balance, positions, quote, risk limit, "
                "or evidence is insufficient, do not return BUY or SELL."
            ),
        )
        sidecar_calls.append(meta)
        decision = _normalise_decision_payload(decision, tool_results=tool_results, evidence_ids=evidence_ids)

        risk_guard, meta = await _call_finance_stage(
            model=FINANCE_RISK_GUARD_MODEL,
            payload={**decision_payload, "decision": decision},
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

        if risk_guard.get("hard_fail") is True:
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
        }
    except Exception as exc:
        error = FinanceShadowValidationError("sidecar_pipeline_failed", details={"stage_error": type(exc).__name__})
        failure_payload = {
            "action": "NO_CONTEXT",
            "symbol": str(agent_state.get("symbol") or ""),
            "market": str(agent_state.get("market") or ""),
            "reason": f"sidecar_pipeline_failed:{type(exc).__name__}",
        }
        record = build_finance_shadow_failure_record(error, failure_payload, tool_results={})
        logger.warning("local_finance_sidecar_pipeline_failed", error=type(exc).__name__)
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
