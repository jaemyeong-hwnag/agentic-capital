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
    checks = [
        check_local_agent_health(),
        check_finance_sidecar_health(),
        check_psychology_sidecar_health(),
        await check_database_health(),
    ]
    ok = all(bool(check.get("ok")) for check in checks)
    result = {"ok": ok, "checks": checks}
    log = logger.info if ok else logger.warning
    log("runtime_health_check", ok=ok, checks=checks)
    return result
