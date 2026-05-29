"""Deterministic paper-shadow checks for local finance model decisions."""

from __future__ import annotations

import hashlib
import json
from typing import Any

SAFE_ACTIONS = {"CALL_TOOL", "WAIT", "HOLD", "OBSERVE", "REJECT", "NO_CONTEXT"}
TRADE_ACTIONS = {"BUY", "SELL"}
PRE_TRADE_TOOLS = {
    "get_balance",
    "get_positions",
    "get_quote",
    "get_market_session",
    "get_risk_limit",
    "search_rag",
}
REQUIRED_TRADE_RESULTS = PRE_TRADE_TOOLS
ORDER_TOOLS = {
    "submit_order",
    "submit_paper_order",
    "submit_futures_order",
    "place_order",
    "execute_trade",
}
OPEN_MARKET_SESSION_STATES = {"open", "regular", "regular_open"}
CLOSED_MARKET_SESSION_STATES = {"closed", "halted", "suspended", "pre", "preopen", "post", "after_hours"}
PROFIT_GUARANTEE_TERMS = (
    "guaranteed profit",
    "profit guaranteed",
    "risk free profit",
    "sure profit",
    "확정 수익",
    "수익 보장",
    "무조건 수익",
    "손실 없음",
)


class FinanceShadowValidationError(ValueError):
    """Raised when a local finance decision is unsafe for paper shadow."""

    def __init__(self, code: str, *, details: dict[str, Any] | None = None) -> None:
        self.code = code
        self.details = details or {}
        super().__init__(code)


def normalize_finance_action(value: Any) -> str:
    """Normalize model action fields to the supported finance action enum."""
    if not isinstance(value, str):
        return ""
    return value.strip().upper()


def validate_finance_shadow_payload(
    payload: dict[str, Any],
    *,
    tool_results: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate a model decision for paper-shadow recording.

    This gate is intentionally deterministic and offline. It verifies the same
    runtime contract expected from the finance sidecars without submitting an
    order or calling a paid provider.
    """
    action = normalize_finance_action(payload.get("action") or payload.get("decision") or payload.get("status"))
    if not action:
        raise FinanceShadowValidationError("missing_action")
    if action not in SAFE_ACTIONS and action not in TRADE_ACTIONS:
        raise FinanceShadowValidationError("unknown_action", details={"action": action})

    planned_tools = _extract_tool_names(payload)
    forbidden_tools = sorted(planned_tools & ORDER_TOOLS)
    if forbidden_tools:
        raise FinanceShadowValidationError("order_tool_in_shadow_plan", details={"forbidden_tools": forbidden_tools})

    evidence_ids = _string_list(payload.get("evidence_ids") or payload.get("evidence") or [])
    _reject_profit_guarantee(payload)

    merged_tool_results = _merge_tool_results(payload.get("tool_results"), tool_results)
    result_names = set(merged_tool_results)
    missing_results = sorted(REQUIRED_TRADE_RESULTS - result_names)

    if action == "CALL_TOOL":
        missing_requested = sorted((set(missing_results) | PRE_TRADE_TOOLS) & planned_tools)
        if missing_results and not missing_requested:
            raise FinanceShadowValidationError(
                "call_tool_missing_required_tools",
                details={"missing_tool_results": missing_results},
            )

    within_risk_limit = True
    notional = 0.0
    if action in TRADE_ACTIONS:
        if missing_results:
            raise FinanceShadowValidationError(
                "trade_missing_tool_results",
                details={"missing_tool_results": missing_results},
            )
        if not evidence_ids:
            raise FinanceShadowValidationError("trade_missing_evidence_ids")
        rag_evidence_ids = _search_rag_evidence_ids(merged_tool_results)
        if not rag_evidence_ids:
            raise FinanceShadowValidationError("trade_missing_rag_evidence")
        uncovered_evidence_ids = sorted(set(evidence_ids) - set(rag_evidence_ids))
        if uncovered_evidence_ids:
            raise FinanceShadowValidationError(
                "trade_uncovered_evidence_ids",
                details={
                    "uncovered_evidence_ids": uncovered_evidence_ids,
                    "rag_evidence_ids": sorted(rag_evidence_ids),
                },
            )
        quote_mismatch = _quote_context_mismatch(payload, merged_tool_results)
        if quote_mismatch is not None:
            raise FinanceShadowValidationError("trade_quote_context_mismatch", details=quote_mismatch)

        notional = _trade_notional(payload, merged_tool_results)
        if notional <= 0:
            raise FinanceShadowValidationError("trade_missing_notional")
        limit_violation = _trade_limit_violation(action, notional, merged_tool_results)
        within_risk_limit = limit_violation is None
        if limit_violation is not None:
            code, details = limit_violation
            raise FinanceShadowValidationError(code, details=details)
        if action == "SELL":
            quantity = _trade_quantity(payload)
            if quantity <= 0:
                raise FinanceShadowValidationError("trade_missing_position_quantity")
            owned_quantity = _owned_position_quantity(payload, merged_tool_results)
            if quantity > owned_quantity:
                raise FinanceShadowValidationError(
                    "trade_exceeds_position",
                    details={
                        "symbol": str(payload.get("symbol") or payload.get("ticker") or ""),
                        "requested_quantity": quantity,
                        "owned_quantity": owned_quantity,
                    },
                )
        if not _market_session_is_open(merged_tool_results):
            raise FinanceShadowValidationError("trade_when_market_closed")

    return {
        "action": action,
        "symbol": str(payload.get("symbol") or payload.get("ticker") or ""),
        "market": str(payload.get("market") or ""),
        "quantity": _trade_quantity(payload) if action in TRADE_ACTIONS else 0.0,
        "price": _trade_price(payload, merged_tool_results) if action in TRADE_ACTIONS else 0.0,
        "order_type": str(payload.get("order_type") or "market"),
        "planned_tools": sorted(planned_tools),
        "missing_tool_results": missing_results,
        "evidence_ids": evidence_ids,
        "notional": notional,
        "within_risk_limit": within_risk_limit,
        "paper_trade_only": True,
        "would_submit_order": action in TRADE_ACTIONS,
    }


def build_finance_shadow_record(
    payload: dict[str, Any],
    *,
    tool_results: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the paper-shadow decision record persisted by the caller."""
    validation = validate_finance_shadow_payload(payload, tool_results=tool_results)
    record_input = {"payload": payload, "tool_results": tool_results or {}}
    return {
        "decision_id": _stable_id("finance-shadow", record_input),
        "record_type": "finance_paper_shadow_decision",
        **validation,
        "tool_result_names": sorted(_merge_tool_results(payload.get("tool_results"), tool_results)),
    }


def build_finance_shadow_failure_record(
    error: FinanceShadowValidationError,
    payload: dict[str, Any],
    *,
    tool_results: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Turn an unsafe raw model output into a deterministic learning record."""
    record_input = {"code": error.code, "payload": payload, "tool_results": tool_results or {}}
    return {
        "failure_id": _stable_id("finance-shadow-failure", record_input),
        "record_type": "raw_model_failure",
        "failure_type": error.code,
        "details": error.details,
        "action": normalize_finance_action(payload.get("action") or payload.get("decision") or payload.get("status")),
        "symbol": str(payload.get("symbol") or payload.get("ticker") or ""),
        "planned_tools": sorted(_extract_tool_names(payload)),
        "evidence_ids": _string_list(payload.get("evidence_ids") or []),
        "paper_trade_only": True,
        "retrain_candidate": error.code
        in {
            "order_tool_in_shadow_plan",
            "trade_missing_tool_results",
            "trade_missing_evidence_ids",
            "trade_missing_rag_evidence",
            "trade_uncovered_evidence_ids",
            "trade_quote_context_mismatch",
            "trade_missing_notional",
            "trade_exceeds_risk_limit",
            "trade_exceeds_available_cash",
            "trade_missing_position_quantity",
            "trade_exceeds_position",
            "trade_when_market_closed",
            "call_tool_loop_with_sufficient_tool_evidence",
            "profit_guarantee_expression",
            "risk_guard_hard_fail",
        },
    }


def _extract_tool_names(payload: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("required_tools", "tools", "tool_plan", "tool_calls", "calls"):
        value = payload.get(key)
        if isinstance(value, str):
            names.add(value.strip())
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    names.add(item.strip())
                elif isinstance(item, dict):
                    name = item.get("tool") or item.get("name") or item.get("function")
                    if isinstance(name, str):
                        names.add(name.strip())
    return {name for name in names if name}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value:
        return [value]
    return []


def _merge_tool_results(*sources: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for source in sources:
        if isinstance(source, dict):
            for key, value in source.items():
                merged[str(key)] = value
        elif isinstance(source, list):
            for item in source:
                if isinstance(item, dict):
                    name = item.get("tool") or item.get("name")
                    if isinstance(name, str):
                        merged[name] = item.get("result", item)
    return merged


def _reject_profit_guarantee(payload: dict[str, Any]) -> None:
    text_fields = [
        payload.get("reason"),
        payload.get("rationale"),
        payload.get("final_answer"),
        payload.get("message"),
    ]
    text = " ".join(str(field) for field in text_fields if field).lower()
    if any(term in text for term in PROFIT_GUARANTEE_TERMS):
        raise FinanceShadowValidationError("profit_guarantee_expression")


def _trade_notional(payload: dict[str, Any], tool_results: dict[str, Any]) -> float:
    quantity = _trade_quantity(payload)
    quote_price = _float(_nested(tool_results, "get_quote", "price"))
    if quantity > 0 and quote_price > 0:
        return quantity * quote_price
    explicit = _float(payload.get("notional") or payload.get("order_value"))
    if explicit > 0:
        return explicit
    payload_price = _float(payload.get("price"))
    return quantity * payload_price


def _trade_quantity(payload: dict[str, Any]) -> float:
    return _float(payload.get("quantity") or payload.get("qty") or _nested(payload, "order", "quantity"))


def _trade_price(payload: dict[str, Any], tool_results: dict[str, Any]) -> float:
    explicit = _float(payload.get("price") or _nested(payload, "order", "price"))
    if explicit > 0:
        return explicit
    return _float(_nested(tool_results, "get_quote", "price"))


def _quote_context_mismatch(payload: dict[str, Any], tool_results: dict[str, Any]) -> dict[str, Any] | None:
    quote = tool_results.get("get_quote")
    if not isinstance(quote, dict):
        return None
    expected_symbol = str(payload.get("symbol") or payload.get("ticker") or "").strip()
    quote_symbol = str(quote.get("symbol") or quote.get("ticker") or "").strip()
    expected_market = str(payload.get("market") or "").strip().lower()
    quote_market = str(quote.get("market") or "").strip().lower()
    mismatches: dict[str, Any] = {}
    if expected_symbol and quote_symbol and expected_symbol != quote_symbol:
        mismatches["symbol"] = {"expected": expected_symbol, "actual": quote_symbol}
    if expected_market and quote_market and expected_market != quote_market:
        mismatches["market"] = {"expected": expected_market, "actual": quote_market}
    return mismatches or None


def _owned_position_quantity(payload: dict[str, Any], tool_results: dict[str, Any]) -> float:
    positions = tool_results.get("get_positions")
    if not isinstance(positions, list):
        return 0.0
    symbol = str(payload.get("symbol") or payload.get("ticker") or "").strip()
    market = str(payload.get("market") or "").strip().lower()
    owned = 0.0
    for position in positions:
        if not isinstance(position, dict):
            continue
        position_symbol = str(position.get("symbol") or position.get("ticker") or "").strip()
        position_market = str(position.get("market") or "").strip().lower()
        if symbol and position_symbol and position_symbol != symbol:
            continue
        if market and position_market and position_market != market:
            continue
        owned += _float(position.get("quantity") or position.get("qty"))
    return owned


def _search_rag_evidence_ids(tool_results: dict[str, Any]) -> list[str]:
    rag = tool_results.get("search_rag")
    if not isinstance(rag, dict):
        return []
    ids = _string_list(rag.get("evidence_ids") or [])
    if ids:
        return ids
    evidence = rag.get("evidence")
    if not isinstance(evidence, list):
        return []
    extracted: list[str] = []
    for idx, item in enumerate(evidence):
        if not isinstance(item, dict):
            continue
        evidence_id = item.get("id") or item.get("evidence_id") or item.get("doc_id") or item.get("chunk_id")
        extracted.append(str(evidence_id or f"rag-{idx}"))
    return extracted


def _trade_limit_violation(action: str, notional: float, tool_results: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    risk = tool_results.get("get_risk_limit")
    balance = tool_results.get("get_balance")
    max_order_value = _first_float(
        risk,
        "max_order_value",
        "max_trade_value",
        "per_trade_limit",
        "max_notional",
    )
    if max_order_value > 0 and notional > max_order_value:
        return "trade_exceeds_risk_limit", {
            "action": action,
            "notional": notional,
            "max_order_value": max_order_value,
        }
    if action == "BUY":
        available = _first_float(balance, "available", "available_cash", "cash")
        if available > 0 and notional > available:
            return "trade_exceeds_available_cash", {
                "action": action,
                "notional": notional,
                "available_cash": available,
            }
    return None


def _market_session_is_open(tool_results: dict[str, Any]) -> bool:
    session = tool_results.get("get_market_session")
    if not isinstance(session, dict):
        return False
    if session.get("is_open") is False or session.get("regular_session") is False:
        return False
    state = str(session.get("state") or session.get("session") or "").lower()
    if state in CLOSED_MARKET_SESSION_STATES:
        return False
    if state in OPEN_MARKET_SESSION_STATES:
        return True
    return session.get("is_open") is True or session.get("regular_session") is True


def _nested(mapping: Any, *keys: str) -> Any:
    current = mapping
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_float(mapping: Any, *keys: str) -> float:
    if not isinstance(mapping, dict):
        return 0.0
    for key in keys:
        value = _float(mapping.get(key))
        if value > 0:
            return value
    return 0.0


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _stable_id(prefix: str, value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"
