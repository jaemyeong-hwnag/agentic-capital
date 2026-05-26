"""Readiness and smoke checks for the local psychology sidecar."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from agentic_capital.config import settings

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = structlog.get_logger()

REQUIRED_FIELDS = {"evidence_ids", "confidence", "uncertainty"}
TRADE_ACTIONS = {"BUY", "SELL", "ORDER", "SUBMIT_ORDER", "PLACE_ORDER"}
DISALLOWED_DOWNSTREAM = {"trade_decision", "order_execution", "alpha_signal"}
CLINICAL_TERMS = ("diagnosis", "treatment", "therapy", "prescription", "진단", "치료", "처방")


class LocalPsychologyRuntimeError(RuntimeError):
    """Raised when the configured local psychology runtime is not usable."""


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _gateway_root(base_url: str) -> str:
    root = base_url.rstrip("/")
    return root[:-3] if root.endswith("/v1") else root


def _expected_model() -> str:
    return settings.local_psychology_expected_health_model.strip() or settings.local_psychology_model.strip()


def _auth_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.local_psychology_api_key:
        headers["Authorization"] = f"Bearer {settings.local_psychology_api_key}"
    return headers


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
        raise LocalPsychologyRuntimeError("local_psychology_health_missing_model")

    actual_lower = actual_model.lower()
    expected_lower = expected_model.lower()
    if expected_lower.startswith("psychology_") and (
        actual_lower.startswith("finance_") or actual_lower.startswith("health")
    ):
        raise LocalPsychologyRuntimeError(
            f"local_psychology_model_category_mismatch: expected={expected_model} actual={actual_model}"
        )
    if actual_model != expected_model:
        raise LocalPsychologyRuntimeError(
            f"local_psychology_model_mismatch: expected={expected_model} actual={actual_model}"
        )
    if payload.get("llama_reachable") is False:
        raise LocalPsychologyRuntimeError("local_psychology_llama_unreachable")
    if payload.get("ok") is False:
        raise LocalPsychologyRuntimeError("local_psychology_health_not_ok")
    return actual_model


def check_local_psychology_health() -> dict[str, Any]:
    """Check `/healthz` and verify that it is the expected psychology service."""
    expected_model = _expected_model()
    health_url = _join_url(_gateway_root(settings.local_psychology_base_url), "/healthz")
    try:
        response = httpx.get(health_url, timeout=settings.local_llm_health_timeout_seconds)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise LocalPsychologyRuntimeError(f"local_psychology_health_unavailable: {health_url}") from exc
    if not isinstance(payload, dict):
        raise LocalPsychologyRuntimeError("local_psychology_health_invalid_payload")

    actual_model = _validate_health_payload(payload, expected_model)
    return {
        "health_url": health_url,
        "expected_model": expected_model,
        "actual_model": actual_model,
        "ok": True,
    }


def _extract_content(payload: dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"].get("content", "")
    except (KeyError, IndexError, TypeError) as exc:
        raise LocalPsychologyRuntimeError("local_psychology_smoke_missing_content") from exc
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


def _walk_values(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for nested in value.values():
            yield from _walk_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_values(nested)
    else:
        yield value


def _normalize_text(value: Any) -> str:
    return value.strip().upper() if isinstance(value, str) else ""


def _rag_evidence_ids(response_payload: dict[str, Any]) -> list[str]:
    rag = response_payload.get("rag")
    if not isinstance(rag, dict):
        return []
    retrieved = rag.get("retrieved")
    if not isinstance(retrieved, list):
        return []

    evidence_ids: list[str] = []
    for item in retrieved:
        if not isinstance(item, dict):
            continue
        evidence_id = item.get("doc_id") or item.get("chunk_id")
        if isinstance(evidence_id, str) and evidence_id and evidence_id not in evidence_ids:
            evidence_ids.append(evidence_id)
    return evidence_ids


def _schema_repair_payload(content: str, response_payload: dict[str, Any]) -> dict[str, Any]:
    evidence_ids = _rag_evidence_ids(response_payload)
    return {
        "signals": [],
        "agent_state_patch": {},
        "evidence_ids": evidence_ids,
        "confidence": 0.0,
        "uncertainty": [
            "schema_unstable: local psychology sidecar returned non-parseable JSON",
            f"raw_preview: {content[:180]}",
        ],
        "risk_tags": ["schema_unstable"],
        "allowed_downstream_use": "context_only",
        "repair_applied": "invalid_json_to_context_only",
    }


def _reject_trade_action_leak(payload: dict[str, Any]) -> None:
    for key in ("action", "decision", "trade_action", "order_action", "signal"):
        action = _normalize_text(payload.get(key))
        if action in TRADE_ACTIONS:
            raise LocalPsychologyRuntimeError(f"local_psychology_trade_action_leak: {key}={action}")

    for value in _walk_values(payload):
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        if any(term in lowered for term in ("submit_order", "place order", "execute order", "주문 실행")):
            raise LocalPsychologyRuntimeError("local_psychology_order_instruction_leak")


def _reject_clinical_claim(payload: dict[str, Any]) -> None:
    for value in _walk_values(payload):
        if isinstance(value, str) and any(term in value.lower() for term in CLINICAL_TERMS):
            raise LocalPsychologyRuntimeError("local_psychology_clinical_claim")


def validate_psychology_context_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate a psychology sidecar response before it can affect agent state."""
    missing = sorted(REQUIRED_FIELDS - set(payload))
    if missing:
        raise LocalPsychologyRuntimeError(f"local_psychology_schema_missing_required: {','.join(missing)}")

    evidence_ids = payload.get("evidence_ids")
    uncertainty = payload.get("uncertainty")
    confidence = payload.get("confidence")
    if not isinstance(evidence_ids, list):
        raise LocalPsychologyRuntimeError("local_psychology_evidence_ids_not_array")
    if not isinstance(uncertainty, list):
        raise LocalPsychologyRuntimeError("local_psychology_uncertainty_not_array")
    if not isinstance(confidence, int | float) or not 0.0 <= float(confidence) <= 1.0:
        raise LocalPsychologyRuntimeError("local_psychology_confidence_out_of_bounds")

    downstream_use = str(payload.get("allowed_downstream_use", "context_only")).lower()
    if downstream_use in DISALLOWED_DOWNSTREAM:
        raise LocalPsychologyRuntimeError(f"local_psychology_disallowed_downstream_use: {downstream_use}")

    _reject_trade_action_leak(payload)
    _reject_clinical_claim(payload)
    return {
        "evidence_count": len(evidence_ids),
        "confidence": float(confidence),
        "uncertainty_count": len(uncertainty),
        "allowed_downstream_use": downstream_use,
    }


def run_local_psychology_smoke() -> dict[str, Any]:
    """Run a context-only psychology smoke query against the local gateway."""
    chat_url = _join_url(settings.local_psychology_base_url, "/chat/completions")
    request_payload = {
        "model": settings.local_psychology_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only JSON with evidence_ids, confidence, uncertainty, risk_tags, "
                    "agent_state_patch, and allowed_downstream_use. Do not output BUY, SELL, "
                    "orders, capital changes, clinical diagnosis, treatment, or therapy claims."
                ),
            },
            {
                "role": "user",
                "content": (
                    "psychology-startup-smoke: agent_id=CEO-Alpha; recent trace says the agent asked "
                    "whether to BUY 005930 after two losses, then avoided checking risk limits. "
                    "Return psychology context only for recorder/risk-guard support."
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
            timeout=settings.local_psychology_timeout_seconds,
        )
        response.raise_for_status()
        response_payload = response.json()
        content = _extract_content(response_payload)
    except Exception as exc:
        raise LocalPsychologyRuntimeError(f"local_psychology_smoke_unavailable: {chat_url}") from exc

    parsed = _extract_json_object(content)
    if parsed is None:
        parsed = _schema_repair_payload(content, response_payload)

    validated = validate_psychology_context_payload(parsed)
    return {
        "chat_url": chat_url,
        "model": settings.local_psychology_model,
        **validated,
        "repair_applied": parsed.get("repair_applied"),
        "ok": True,
    }


def validate_local_psychology_runtime() -> dict[str, Any]:
    """Validate the psychology sidecar as observer/context only."""
    if not settings.local_psychology_readiness_required:
        return {"ok": True, "skipped": "local_psychology_readiness_required_false"}

    health = check_local_psychology_health()
    smoke = run_local_psychology_smoke() if settings.local_psychology_smoke_enabled else {"skipped": True}
    logger.info(
        "local_psychology_runtime_ready",
        model=health["actual_model"],
        smoke_evidence_count=smoke.get("evidence_count"),
    )
    return {"ok": True, "health": health, "smoke": smoke}
