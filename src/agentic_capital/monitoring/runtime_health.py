"""Runtime health checks for local paper trading services."""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from sqlalchemy import text

from agentic_capital.adapters.llm.local_finance_runtime import (
    FINANCE_DECISION_MODEL,
    FINANCE_RAG_QUERY_MODEL,
    FINANCE_RISK_GUARD_MODEL,
    FINANCE_TOOL_PLANNER_MODEL,
    check_local_finance_health,
    check_local_finance_pipeline_health,
)
from agentic_capital.adapters.llm.local_psychology_runtime import check_local_psychology_health
from agentic_capital.adapters.llm.router import is_local_llm_enabled
from agentic_capital.config import settings
from agentic_capital.infra.database import async_session

logger = structlog.get_logger()

FINANCE_MODEL_INVENTORY = [
    FINANCE_RAG_QUERY_MODEL,
    "finance_embedding_model",
    "finance_reranker_model",
    "finance_evidence_summarizer_model",
    FINANCE_TOOL_PLANNER_MODEL,
    FINANCE_DECISION_MODEL,
    FINANCE_RISK_GUARD_MODEL,
    "finance_eval_judge_model",
    "finance_qa_generator_model",
    "finance_reflection_model",
]

PSYCHOLOGY_MODEL_INVENTORY = [
    "psychology_memory_retriever_model",
    "psychology_behavior_bias_model",
    "psychology_drift_model",
    "psychology_emotion_model",
    "psychology_model_suite",
    "psychology_profile_model",
    "psychology_reflection_model",
    "psychology_social_dynamics_model",
]


def _ok(name: str, **details: Any) -> dict[str, Any]:
    return {"name": name, "ok": True, **details}


def _fail(name: str, exc: Exception) -> dict[str, Any]:
    return {
        "name": name,
        "ok": False,
        "error": type(exc).__name__,
        "message": str(exc)[:240],
    }


def _base_url_health(base_url: str, expected_model: str) -> dict[str, Any]:
    root_url = base_url.rstrip("/")[:-3] if base_url.rstrip("/").endswith("/v1") else base_url.rstrip("/")
    health_urls = [f"{root_url}/healthz", f"{root_url}/health"]
    last_exc: Exception | None = None
    health_url = health_urls[0]
    try:
        for health_url in health_urls:
            try:
                response = httpx.get(health_url, timeout=settings.local_llm_health_timeout_seconds)
                response.raise_for_status()
                payload = response.json()
                break
            except Exception as exc:
                last_exc = exc
        else:
            raise last_exc or RuntimeError("runtime_health_unavailable")
    except Exception as exc:
        return _fail(expected_model, exc) | {"health_url": health_url}

    actual_model = ""
    if isinstance(payload, dict):
        actual_model = str(payload.get("model") or payload.get("llm_model") or payload.get("service") or "")
    return _ok(expected_model, health_url=health_url, actual_model=actual_model)


def _parse_model_url_map(raw: str) -> dict[str, str]:
    """Parse comma-separated `model=url` entries for optional validation sidecars."""
    urls: dict[str, str] = {}
    for entry in raw.split(","):
        item = entry.strip()
        if not item:
            continue
        if "=" not in item:
            urls[item] = ""
            continue
        model, url = item.split("=", 1)
        model = model.strip()
        url = url.strip()
        if model:
            urls[model] = url
    return urls


def _strict_model_url_health(model: str, base_url: str) -> dict[str, Any]:
    if not base_url:
        return {
            "name": model,
            "ok": False,
            "coverage": "validation_url_missing",
            "message": "validation base URL is not configured",
        }
    result = _base_url_health(base_url, model)
    result["coverage"] = "validation_sidecar"
    actual_model = str(result.get("actual_model") or "")
    if result.get("ok") and actual_model and actual_model != model:
        return {
            **result,
            "ok": False,
            "error": "ModelMismatch",
            "message": f"expected={model} actual={actual_model}",
        }
    if result.get("ok") and not actual_model:
        return {
            **result,
            "ok": False,
            "error": "MissingModel",
            "message": "health payload did not identify the model",
        }
    return result


def _finance_runtime_models(finance_check: dict[str, Any]) -> set[str]:
    models: set[str] = set()
    primary = finance_check.get("primary")
    if isinstance(primary, dict) and primary.get("ok"):
        actual = str(primary.get("actual_model") or "")
        if actual:
            models.add(actual)
    pipeline = finance_check.get("pipeline")
    stages = pipeline.get("stages") if isinstance(pipeline, dict) else None
    if isinstance(stages, dict):
        for model, stage in stages.items():
            if isinstance(stage, dict) and stage.get("ok"):
                models.add(str(stage.get("actual_model") or model))
    return models


def _psychology_runtime_models(psychology_check: dict[str, Any]) -> set[str]:
    if not psychology_check.get("ok"):
        return set()
    actual = str(psychology_check.get("actual_model") or "")
    return {actual} if actual else set()


def check_model_inventory_health(
    finance_check: dict[str, Any],
    psychology_check: dict[str, Any],
) -> dict[str, Any]:
    """Report whether every locally trained model is exercised or still unvalidated."""
    finance_runtime = _finance_runtime_models(finance_check)
    psychology_runtime = _psychology_runtime_models(psychology_check)
    finance_urls = _parse_model_url_map(settings.local_finance_validation_base_urls)
    psychology_urls = _parse_model_url_map(settings.local_psychology_validation_base_urls)

    finance_models = []
    for model in FINANCE_MODEL_INVENTORY:
        if model in finance_runtime:
            finance_models.append(_ok(model, coverage="paper_runtime_sidecar"))
        elif model in finance_urls:
            finance_models.append(_strict_model_url_health(model, finance_urls[model]))
        else:
            finance_models.append({
                "name": model,
                "ok": False,
                "coverage": "unvalidated",
                "message": "not checked by paper runtime and no validation sidecar URL configured",
            })

    psychology_models = []
    suite_running = "psychology_model_suite" in psychology_runtime
    for model in PSYCHOLOGY_MODEL_INVENTORY:
        if model in psychology_runtime:
            psychology_models.append(_ok(model, coverage="paper_runtime_sidecar"))
        elif model in psychology_urls:
            psychology_models.append(_strict_model_url_health(model, psychology_urls[model]))
        else:
            psychology_models.append({
                "name": model,
                "ok": False,
                "coverage": "suite_only" if suite_running else "unvalidated",
                "message": (
                    "covered only through psychology_model_suite; no direct validation sidecar URL configured"
                    if suite_running
                    else "not checked by paper runtime and no validation sidecar URL configured"
                ),
            })

    unvalidated = [
        model["name"]
        for model in [*finance_models, *psychology_models]
        if not model.get("ok")
    ]
    return {
        "name": "local_model_inventory",
        "ok": not unvalidated,
        "blocking": False,
        "finance_models": finance_models,
        "psychology_models": psychology_models,
        "unvalidated_models": unvalidated,
    }


def check_local_agent_health() -> dict[str, Any]:
    """Check the CEO/Analyst local agent runtime without using finance decision model."""
    if not is_local_llm_enabled():
        return _ok("agent_llm", skipped="local_llm_disabled")
    base_url = settings.local_agent_llm_base_url.strip()
    if not base_url:
        return _fail("agent_llm", RuntimeError("LOCAL_AGENT_LLM_BASE_URL missing"))
    return _base_url_health(base_url, settings.local_agent_llm_model.strip() or "agentic_capital_react_model")


def check_finance_sidecar_health() -> dict[str, Any]:
    """Check primary finance decision and configured finance stage sidecars."""
    try:
        primary = check_local_finance_health()
    except Exception as exc:
        primary = _fail(FINANCE_DECISION_MODEL, exc)
    try:
        pipeline = check_local_finance_pipeline_health()
    except Exception as exc:
        pipeline = _fail("finance_pipeline", exc)
    return {
        "name": "finance_sidecars",
        "ok": bool(primary.get("ok")) and bool(pipeline.get("ok")),
        "primary": primary,
        "pipeline": pipeline,
        "expected_stages": [
            FINANCE_RAG_QUERY_MODEL,
            FINANCE_TOOL_PLANNER_MODEL,
            FINANCE_DECISION_MODEL,
            FINANCE_RISK_GUARD_MODEL,
        ],
    }


def check_psychology_sidecar_health() -> dict[str, Any]:
    """Check psychology observer sidecar health."""
    try:
        health = check_local_psychology_health()
    except Exception as exc:
        return _fail("psychology_sidecar", exc)
    return {"name": "psychology_sidecar", **health}


async def check_database_health() -> dict[str, Any]:
    """Check DB connectivity used by recorder and monitoring."""
    try:
        async with async_session() as session:
            await session.execute(text("select 1"))
    except Exception as exc:
        return _fail("database", exc)
    return _ok("database")


async def collect_runtime_health() -> dict[str, Any]:
    """Collect local runtime health for every service needed by paper trading."""
    agent_check = check_local_agent_health()
    finance_check = check_finance_sidecar_health()
    psychology_check = check_psychology_sidecar_health()
    checks = [
        agent_check,
        finance_check,
        psychology_check,
        await check_database_health(),
    ]
    if settings.local_model_inventory_healthcheck_enabled:
        checks.append(check_model_inventory_health(finance_check, psychology_check))
    ok = all(
        bool(check.get("ok"))
        for check in checks
        if check.get("blocking", True) is not False
    )
    result = {"ok": ok, "checks": checks}
    log = logger.info if ok else logger.warning
    log("runtime_health_check", ok=ok, checks=checks)
    return result
