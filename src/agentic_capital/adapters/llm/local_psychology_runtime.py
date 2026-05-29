"""Readiness and smoke checks for the local psychology sidecar."""

from __future__ import annotations

import json
import hashlib
import time
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from agentic_capital.config import settings

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = structlog.get_logger()

REQUIRED_FIELDS = {"evidence_ids", "confidence", "uncertainty", "risk_tags", "allowed_downstream_use"}
TRADE_ACTIONS = {"BUY", "SELL", "ORDER", "SUBMIT_ORDER", "PLACE_ORDER"}
DISALLOWED_DOWNSTREAM = {"trade_decision", "order_execution", "alpha_signal"}
ALLOWED_DOWNSTREAM = {"context_only", "record_only", "risk_context_not_alpha", "agent_state_context"}
CLINICAL_TERMS = ("diagnosis", "treatment", "therapy", "prescription", "진단", "치료", "처방")
ORDER_INSTRUCTION_TERMS = ("submit_order", "place order", "execute order", "주문 실행")
NEGATED_ORDER_SAFETY_TERMS = (
    "must not",
    "never",
    "no ",
    "not ",
    "without ",
    "forbidden",
    "disallow",
    "prevent",
    "avoid",
    "금지",
    "하지 말",
    "없",
)
ORDER_MUTATION_KEYS = {
    "quantity",
    "qty",
    "order_quantity",
    "position_size",
    "position_size_pct",
    "order_permission",
    "live_order_enabled",
    "live_orders_enabled",
    "capital",
    "capital_delta",
    "capital_allocation",
    "risk_limit",
    "risk_limit_override",
    "max_order_value",
    "target_weight",
}
SOFT_CONTEXT_KEYS = {"risk_tags", "confidence", "uncertainty", "evidence_ids", "agent_state_patch"}
FORCED_DOWNSTREAM_USE = "context_only"


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


def _is_negated_order_safety_statement(value: str) -> bool:
    lowered = value.lower()
    if not any(term in lowered for term in ORDER_INSTRUCTION_TERMS):
        return False
    return any(term in lowered for term in NEGATED_ORDER_SAFETY_TERMS)


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


def _raw_output_fingerprint(content: str) -> list[str]:
    encoded = content.encode("utf-8", errors="replace")
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    return [f"raw_output_sha256:{digest}", f"raw_output_chars:{len(content)}"]


def _schema_repair_payload(content: str, response_payload: dict[str, Any]) -> dict[str, Any]:
    evidence_ids = _rag_evidence_ids(response_payload)
    return {
        "signals": [],
        "agent_state_patch": {},
        "evidence_ids": evidence_ids,
        "confidence": 0.0,
        "uncertainty": [
            "raw_model_output_invalid_json",
            "deterministic_context_only_repair_applied",
            *_raw_output_fingerprint(content),
        ],
        "risk_tags": ["schema_repaired_context_only"],
        "allowed_downstream_use": "context_only",
        "schema_status": "schema_repaired_context_only",
        "repair_applied": "invalid_json_to_context_only",
    }


def _validation_repair_payload(
    parsed: dict[str, Any],
    *,
    content: str,
    response_payload: dict[str, Any],
    error: LocalPsychologyRuntimeError,
) -> dict[str, Any]:
    evidence_ids = _coerce_string_list(parsed.get("evidence_ids"))
    if not evidence_ids:
        evidence_ids = _rag_evidence_ids(response_payload)
    return {
        "signals": [],
        "agent_state_patch": {},
        "evidence_ids": evidence_ids,
        "confidence": 0.0,
        "uncertainty": [
            "raw_model_output_failed_context_only_validator",
            str(error),
            *_raw_output_fingerprint(content),
        ],
        "risk_tags": ["schema_repaired_context_only", "psychology_validation_repaired"],
        "allowed_downstream_use": "context_only",
        "schema_status": "schema_repaired_context_only",
        "repair_applied": "validation_failure_to_context_only",
    }


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value in (None, ""):
        return []
    return [str(value)]


def _complete_schema_payload(
    payload: dict[str, Any],
    *,
    content: str,
    response_payload: dict[str, Any],
) -> dict[str, Any]:
    """Complete model JSON into the context-only psychology schema before validation."""
    completed = dict(payload)
    completion_notes: list[str] = []

    evidence_ids = completed.get("evidence_ids")
    if not isinstance(evidence_ids, list):
        evidence_ids = _coerce_string_list(evidence_ids)
        if not evidence_ids:
            evidence_ids = _rag_evidence_ids(response_payload)
        completed["evidence_ids"] = evidence_ids
        completion_notes.append("evidence_ids_completed")
    else:
        completed["evidence_ids"] = _coerce_string_list(evidence_ids)

    confidence = completed.get("confidence")
    if not isinstance(confidence, int | float) or not 0.0 <= float(confidence) <= 1.0:
        completed["confidence"] = 0.0
        completion_notes.append("confidence_defaulted")

    uncertainty = completed.get("uncertainty")
    if not isinstance(uncertainty, list):
        completed["uncertainty"] = _coerce_string_list(uncertainty)
        completion_notes.append("uncertainty_completed")
    else:
        completed["uncertainty"] = _coerce_string_list(uncertainty)

    risk_tags = completed.get("risk_tags")
    if not isinstance(risk_tags, list):
        completed["risk_tags"] = _coerce_string_list(risk_tags)
        completion_notes.append("risk_tags_completed")
    else:
        completed["risk_tags"] = _coerce_string_list(risk_tags)

    downstream_use = str(completed.get("allowed_downstream_use", "")).lower()
    if downstream_use != FORCED_DOWNSTREAM_USE:
        if downstream_use in DISALLOWED_DOWNSTREAM:
            completed["risk_tags"].append("disallowed_downstream_use_suppressed")
        completed["allowed_downstream_use"] = FORCED_DOWNSTREAM_USE
        completion_notes.append("allowed_downstream_use_forced_context_only")

    if completion_notes:
        completed.setdefault("repair_applied", "schema_completed")
        completed["uncertainty"].append(f"schema_completed: {','.join(completion_notes)}")
        if "schema_completed" not in completed["risk_tags"]:
            completed["risk_tags"].append("schema_completed")
        if content and "raw_output_sha256:" not in " ".join(completed["uncertainty"]):
            completed["uncertainty"].extend(_raw_output_fingerprint(content))

    return completed


def _summary_text(value: Any, *, limit: int = 500) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else f"{compact[:limit].rstrip()}..."


def _reject_trade_action_leak(payload: dict[str, Any]) -> None:
    for key in ("action", "decision", "trade_action", "order_action", "signal"):
        action = _normalize_text(payload.get(key))
        if action in TRADE_ACTIONS:
            raise LocalPsychologyRuntimeError(f"local_psychology_trade_action_leak: {key}={action}")

    for value in _walk_values(payload):
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        if any(term in lowered for term in ORDER_INSTRUCTION_TERMS) and not _is_negated_order_safety_statement(value):
            raise LocalPsychologyRuntimeError("local_psychology_order_instruction_leak")


def _reject_order_mutation(payload: dict[str, Any]) -> None:
    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                key_text = str(key)
                if key_text in ORDER_MUTATION_KEYS:
                    raise LocalPsychologyRuntimeError(f"local_psychology_order_mutation_key: {path}{key_text}")
                walk(nested, f"{path}{key_text}.")
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                walk(nested, f"{path}{index}.")

    walk(payload)


def _reject_clinical_claim(payload: dict[str, Any]) -> None:
    for value in _walk_values(payload):
        if isinstance(value, str) and any(term in value.lower() for term in CLINICAL_TERMS):
            raise LocalPsychologyRuntimeError("local_psychology_clinical_claim")


def normalize_psychology_context(payload: dict[str, Any]) -> dict[str, Any]:
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

    risk_tags = payload.get("risk_tags")
    if not isinstance(risk_tags, list):
        raise LocalPsychologyRuntimeError("local_psychology_risk_tags_not_array")

    downstream_use = str(payload.get("allowed_downstream_use")).lower()
    if downstream_use in DISALLOWED_DOWNSTREAM:
        raise LocalPsychologyRuntimeError(f"local_psychology_disallowed_downstream_use: {downstream_use}")
    if downstream_use not in ALLOWED_DOWNSTREAM:
        downstream_use = FORCED_DOWNSTREAM_USE
    downstream_use = FORCED_DOWNSTREAM_USE

    _reject_trade_action_leak(payload)
    _reject_order_mutation(payload)
    _reject_clinical_claim(payload)

    agent_state_patch = payload.get("agent_state_patch") or {}
    if not isinstance(agent_state_patch, dict):
        agent_state_patch = {}

    return {
        "signals": [],
        "agent_state_patch": agent_state_patch,
        "evidence_ids": evidence_ids,
        "confidence": float(confidence),
        "uncertainty": uncertainty,
        "risk_tags": [str(tag) for tag in risk_tags if str(tag)],
        "allowed_downstream_use": downstream_use,
        "use_as": "psychology_context_not_alpha",
        "schema_status": str(payload.get("schema_status") or payload.get("repair_applied") or "validated"),
    }


def validate_psychology_context_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and summarize a psychology sidecar response."""
    normalized = normalize_psychology_context(payload)
    return {
        "evidence_count": len(normalized["evidence_ids"]),
        "confidence": normalized["confidence"],
        "uncertainty_count": len(normalized["uncertainty"]),
        "allowed_downstream_use": normalized["allowed_downstream_use"],
        "schema_status": normalized["schema_status"],
    }


def build_finance_soft_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Reduce psychology output to a finance-safe soft risk context."""
    normalized = normalize_psychology_context(payload)
    return {
        key: normalized[key]
        for key in SOFT_CONTEXT_KEYS
        if normalized.get(key) not in (None, [], {})
    } | {
        "schema_status": normalized["schema_status"],
        "use_as": "soft_risk_context_not_alpha",
        "forbidden_use": [
            "trade_action",
            "order_quantity",
            "order_permission",
            "capital_allocation",
            "risk_limit_override",
        ],
    }


async def run_local_psychology_context(
    *,
    request_id: str,
    agent_context: dict[str, Any],
    input_text: str,
    required_safety: dict[str, Any] | None = None,
    service: str | None = None,
) -> dict[str, Any]:
    """Call psychology sidecar for context-only cycle observation."""
    model = service or settings.local_psychology_model
    chat_url = _join_url(settings.local_psychology_base_url, "/chat/completions")
    request_payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only JSON with signals, agent_state_patch, evidence_ids, confidence, "
                    "uncertainty, risk_tags, and allowed_downstream_use. "
                    "Use allowed_downstream_use=context_only. Include evidence_ids even if the "
                    "only evidence is the cycle trace request_id. "
                    "This is context-only psychology observation for recorder/risk support. Never output BUY, SELL, "
                    "orders, quantities, capital allocation, risk limit overrides, clinical "
                    "diagnosis, treatment, or therapy claims."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "request_id": request_id,
                        "service": model,
                        "agent_context": agent_context,
                        "input_text": _summary_text(input_text, limit=900),
                        "required_safety": required_safety
                        or {
                            "require_evidence_ids": True,
                            "allow_observation_only": True,
                            "no_clinical_diagnosis": True,
                            "no_direct_order": True,
                        },
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
            },
        ],
        "temperature": 0.0,
    }
    started = time.perf_counter()
    response: httpx.Response | None = None
    try:
        async with httpx.AsyncClient(timeout=settings.local_psychology_timeout_seconds) as client:
            response = await client.post(chat_url, headers=_auth_headers(), json=request_payload)
            response.raise_for_status()
            response_payload = response.json()
        content = _extract_content(response_payload)
        parsed = _extract_json_object(content)
        if parsed is None:
            parsed = _schema_repair_payload(content, response_payload)
        else:
            parsed = _complete_schema_payload(parsed, content=content, response_payload=response_payload)
        repair_applied = parsed.get("repair_applied")
        try:
            context = normalize_psychology_context(parsed)
        except LocalPsychologyRuntimeError as exc:
            parsed = _validation_repair_payload(parsed, content=content, response_payload=response_payload, error=exc)
            repair_applied = parsed.get("repair_applied")
            context = normalize_psychology_context(parsed)
        return {
            "ok": True,
            "request_id": request_id,
            "model": model,
            "status_code": getattr(response, "status_code", None),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "context": context,
            "soft_context": build_finance_soft_context(context),
            "repair_applied": repair_applied,
        }
    except Exception as exc:
        return {
            "ok": False,
            "request_id": request_id,
            "model": model,
            "status_code": getattr(response, "status_code", None),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "error": type(exc).__name__,
            "failure_body_summary": _summary_text(getattr(response, "text", "") or str(exc)),
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
                    "agent_state_patch, and allowed_downstream_use=context_only. Do not output BUY, SELL, "
                    "orders, quantities, order permissions, capital changes, risk limit overrides, "
                    "clinical diagnosis, treatment, or therapy claims."
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
    else:
        parsed = _complete_schema_payload(parsed, content=content, response_payload=response_payload)

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
