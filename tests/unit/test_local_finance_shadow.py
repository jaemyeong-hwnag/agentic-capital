"""Offline paper-shadow tests for local finance model decisions."""

import pytest

from agentic_capital.adapters.llm.local_finance_shadow import (
    FinanceShadowValidationError,
    build_finance_shadow_failure_record,
    build_finance_shadow_record,
    validate_finance_shadow_payload,
)


def _complete_tool_results() -> dict:
    return {
        "get_balance": {"available": 1_000_000, "total": 1_000_000, "currency": "KRW"},
        "get_positions": [],
        "get_quote": {"symbol": "005930", "price": 70_000, "market": "kr_stock"},
        "get_ohlcv": {"symbol": "005930", "timeframe": "15m", "candles": [{"close": 70_000}], "count": 1},
        "market_signal": {"candidate_action": "BUY", "confidence": 0.4, "reason": "short_window_positive_momentum"},
        "get_market_session": {"is_open": True, "state": "regular"},
        "get_risk_limit": {"max_order_value": 300_000},
        "search_rag": {"evidence_ids": ["ev-samsung-risk-001"]},
    }


def test_call_tool_record_is_allowed_without_market_context() -> None:
    record = build_finance_shadow_record(
        {
            "action": "CALL_TOOL",
            "symbol": "005930",
            "market": "kr_stock",
            "required_tools": ["get_balance", "get_positions", "get_quote", "get_market_session", "get_risk_limit", "search_rag"],
        }
    )

    assert record["record_type"] == "finance_paper_shadow_decision"
    assert record["paper_trade_only"] is True
    assert record["would_submit_order"] is False
    assert "get_quote" in record["missing_tool_results"]


def test_trade_without_required_tool_results_is_blocked() -> None:
    with pytest.raises(FinanceShadowValidationError, match="trade_missing_tool_results"):
        validate_finance_shadow_payload(
            {
                "action": "BUY",
                "symbol": "005930",
                "quantity": 1,
                "evidence_ids": ["ev-1"],
            }
        )


def test_order_tools_are_forbidden_in_shadow_plan() -> None:
    with pytest.raises(FinanceShadowValidationError, match="order_tool_in_shadow_plan"):
        validate_finance_shadow_payload(
            {
                "action": "CALL_TOOL",
                "symbol": "005930",
                "required_tools": ["get_quote", "submit_paper_order"],
            }
        )


def test_trade_over_risk_limit_is_blocked_and_learnable() -> None:
    payload = {
        "action": "BUY",
        "symbol": "005930",
        "market": "kr_stock",
        "quantity": 10,
        "evidence_ids": ["ev-samsung-risk-001"],
    }

    with pytest.raises(FinanceShadowValidationError) as exc_info:
        validate_finance_shadow_payload(payload, tool_results=_complete_tool_results())

    assert exc_info.value.code == "trade_exceeds_risk_limit"
    failure = build_finance_shadow_failure_record(exc_info.value, payload, tool_results=_complete_tool_results())
    assert failure["record_type"] == "raw_model_failure"
    assert failure["retrain_candidate"] is True


def test_trade_uses_quote_price_over_model_payload_price_for_notional() -> None:
    payload = {
        "action": "BUY",
        "symbol": "005930",
        "market": "kr_stock",
        "quantity": 10,
        "price": 1,
        "evidence_ids": ["ev-samsung-risk-001"],
    }

    with pytest.raises(FinanceShadowValidationError) as exc_info:
        validate_finance_shadow_payload(payload, tool_results=_complete_tool_results())

    assert exc_info.value.code == "trade_exceeds_risk_limit"
    assert exc_info.value.details["notional"] == 700_000
    failure = build_finance_shadow_failure_record(exc_info.value, payload, tool_results=_complete_tool_results())
    assert failure["record_type"] == "raw_model_failure"
    assert failure["retrain_candidate"] is True


def test_trade_uses_paper_order_intent_quantity_for_notional() -> None:
    payload = {
        "action": "BUY",
        "symbol": "005930",
        "market": "kr_stock",
        "paper_order_intent": {
            "symbol": "005930",
            "market": "kr_stock",
            "side": "buy",
            "quantity": 1,
            "paper_trade_only": True,
        },
        "evidence_ids": ["ev-samsung-risk-001"],
    }

    validation = validate_finance_shadow_payload(payload, tool_results=_complete_tool_results())
    record = build_finance_shadow_record(payload, tool_results=_complete_tool_results())

    assert validation["would_submit_order"] is True
    assert validation["notional"] == 70_000
    assert record["would_submit_order"] is True
    assert record["notional"] == 70_000


def test_trade_with_mismatched_quote_symbol_is_blocked_and_learnable() -> None:
    payload = {
        "action": "BUY",
        "symbol": "005930",
        "market": "kr_stock",
        "quantity": 1,
        "evidence_ids": ["ev-samsung-risk-001"],
    }
    tool_results = {
        **_complete_tool_results(),
        "get_quote": {"symbol": "000660", "price": 70_000, "market": "kr_stock"},
        "get_risk_limit": {"max_order_value": 1_000_000},
    }

    with pytest.raises(FinanceShadowValidationError) as exc_info:
        validate_finance_shadow_payload(payload, tool_results=tool_results)

    assert exc_info.value.code == "trade_quote_context_mismatch"
    assert exc_info.value.details["symbol"] == {"expected": "005930", "actual": "000660"}
    failure = build_finance_shadow_failure_record(exc_info.value, payload, tool_results=tool_results)
    assert failure["record_type"] == "raw_model_failure"
    assert failure["retrain_candidate"] is True


def test_buy_over_available_cash_is_blocked_and_learnable() -> None:
    payload = {
        "action": "BUY",
        "symbol": "005930",
        "market": "kr_stock",
        "quantity": 3,
        "evidence_ids": ["ev-samsung-risk-001"],
    }
    tool_results = {
        **_complete_tool_results(),
        "get_balance": {"available": 100_000, "total": 100_000, "currency": "KRW"},
        "get_risk_limit": {"max_order_value": 1_000_000},
    }

    with pytest.raises(FinanceShadowValidationError) as exc_info:
        validate_finance_shadow_payload(payload, tool_results=tool_results)

    assert exc_info.value.code == "trade_exceeds_available_cash"
    assert exc_info.value.details["available_cash"] == 100_000
    failure = build_finance_shadow_failure_record(exc_info.value, payload, tool_results=tool_results)
    assert failure["record_type"] == "raw_model_failure"
    assert failure["retrain_candidate"] is True


def test_trade_missing_notional_is_blocked_and_learnable() -> None:
    payload = {
        "action": "BUY",
        "symbol": "005930",
        "market": "kr_stock",
        "evidence_ids": ["ev-samsung-risk-001"],
    }

    with pytest.raises(FinanceShadowValidationError) as exc_info:
        validate_finance_shadow_payload(payload, tool_results=_complete_tool_results())

    assert exc_info.value.code == "trade_missing_notional"
    failure = build_finance_shadow_failure_record(exc_info.value, payload, tool_results=_complete_tool_results())
    assert failure["record_type"] == "raw_model_failure"
    assert failure["retrain_candidate"] is True


def test_trade_with_fabricated_evidence_id_is_blocked_and_learnable() -> None:
    payload = {
        "action": "BUY",
        "symbol": "005930",
        "market": "kr_stock",
        "quantity": 1,
        "evidence_ids": ["fabricated-evidence"],
    }
    tool_results = {
        **_complete_tool_results(),
        "search_rag": {"evidence_ids": ["ev-samsung-risk-001"]},
    }

    with pytest.raises(FinanceShadowValidationError) as exc_info:
        validate_finance_shadow_payload(payload, tool_results=tool_results)

    assert exc_info.value.code == "trade_uncovered_evidence_ids"
    assert exc_info.value.details["uncovered_evidence_ids"] == ["fabricated-evidence"]
    failure = build_finance_shadow_failure_record(exc_info.value, payload, tool_results=tool_results)
    assert failure["record_type"] == "raw_model_failure"
    assert failure["retrain_candidate"] is True


def test_trade_when_market_closed_is_blocked_and_learnable() -> None:
    payload = {
        "action": "BUY",
        "symbol": "005930",
        "market": "kr_stock",
        "quantity": 1,
        "evidence_ids": ["ev-samsung-risk-001"],
    }
    tool_results = {
        **_complete_tool_results(),
        "get_market_session": {"is_open": False, "regular_session": False, "state": "closed"},
    }

    with pytest.raises(FinanceShadowValidationError) as exc_info:
        validate_finance_shadow_payload(payload, tool_results=tool_results)

    assert exc_info.value.code == "trade_when_market_closed"
    failure = build_finance_shadow_failure_record(exc_info.value, payload, tool_results=tool_results)
    assert failure["record_type"] == "raw_model_failure"
    assert failure["retrain_candidate"] is True


def test_trade_with_unknown_market_session_is_blocked_and_learnable() -> None:
    payload = {
        "action": "BUY",
        "symbol": "005930",
        "market": "kr_stock",
        "quantity": 1,
        "evidence_ids": ["ev-samsung-risk-001"],
    }
    tool_results = {
        **_complete_tool_results(),
        "get_market_session": {},
    }

    with pytest.raises(FinanceShadowValidationError) as exc_info:
        validate_finance_shadow_payload(payload, tool_results=tool_results)

    assert exc_info.value.code == "trade_when_market_closed"
    failure = build_finance_shadow_failure_record(exc_info.value, payload, tool_results=tool_results)
    assert failure["record_type"] == "raw_model_failure"
    assert failure["retrain_candidate"] is True


def test_trade_with_nxt_extended_session_is_still_blocked_for_shadow_execution() -> None:
    payload = {
        "action": "BUY",
        "symbol": "005930",
        "market": "kr_stock",
        "quantity": 1,
        "evidence_ids": ["ev-samsung-risk-001"],
    }
    tool_results = {
        **_complete_tool_results(),
        "get_market_session": {"exchange": "NXT", "state": "extended", "session": "nxt_pre", "is_open": True, "regular_session": False},
    }

    with pytest.raises(FinanceShadowValidationError) as exc_info:
        validate_finance_shadow_payload(payload, tool_results=tool_results)

    assert exc_info.value.code == "trade_when_market_closed"


def test_trade_during_us_premarket_is_allowed() -> None:
    payload = {
        "action": "BUY",
        "symbol": "AAPL",
        "market": "us_stock",
        "quantity": 1,
        "evidence_ids": ["ev-aapl-risk-001"],
    }
    tool_results = {
        "get_balance": {"available": 1_000_000, "total": 1_000_000, "currency": "USD"},
        "get_positions": [],
        "get_quote": {"symbol": "AAPL", "price": 185.0, "market": "us_stock"},
        "get_ohlcv": {"symbol": "AAPL", "timeframe": "15m", "candles": [{"close": 185.0}], "count": 1},
        "market_signal": {"candidate_action": "BUY", "confidence": 0.4, "reason": "short_window_positive_momentum"},
        "get_market_session": {"exchange": "NASDAQ", "state": "pre", "session": "pre", "is_open": True, "regular_session": False},
        "get_risk_limit": {"max_order_value": 1_000_000},
        "search_rag": {"evidence_ids": ["ev-aapl-risk-001"]},
    }

    validation = validate_finance_shadow_payload(payload, tool_results=tool_results)
    assert validation["would_submit_order"] is True


def test_trade_during_night_session_is_allowed_for_kr_options() -> None:
    payload = {
        "action": "BUY",
        "symbol": "K200_CALL_ATM",
        "market": "kr_options",
        "quantity": 1,
        "evidence_ids": ["ev-call-risk-001"],
    }
    tool_results = {
        "get_balance": {"available": 1_000_000, "total": 1_000_000, "currency": "KRW"},
        "get_positions": [],
        "get_quote": {"symbol": "K200_CALL_ATM", "price": 42.0, "market": "kr_options"},
        "get_ohlcv": {"symbol": "K200_CALL_ATM", "timeframe": "15m", "candles": [{"close": 42.0}], "count": 1},
        "market_signal": {"candidate_action": "BUY", "confidence": 0.4, "reason": "short_window_positive_momentum"},
        "get_market_session": {"exchange": "NIGHT", "state": "night", "session": "night", "is_open": True, "regular_session": False},
        "get_risk_limit": {"max_order_value": 1_000_000},
        "search_rag": {"evidence_ids": ["ev-call-risk-001"]},
    }

    validation = validate_finance_shadow_payload(payload, tool_results=tool_results)
    assert validation["would_submit_order"] is True


def test_trade_with_conflicting_market_session_is_blocked_and_learnable() -> None:
    payload = {
        "action": "BUY",
        "symbol": "005930",
        "market": "kr_stock",
        "quantity": 1,
        "evidence_ids": ["ev-samsung-risk-001"],
    }
    tool_results = {
        **_complete_tool_results(),
        "get_market_session": {"state": "closed", "is_open": True, "regular_session": True},
    }

    with pytest.raises(FinanceShadowValidationError) as exc_info:
        validate_finance_shadow_payload(payload, tool_results=tool_results)

    assert exc_info.value.code == "trade_when_market_closed"
    failure = build_finance_shadow_failure_record(exc_info.value, payload, tool_results=tool_results)
    assert failure["record_type"] == "raw_model_failure"
    assert failure["retrain_candidate"] is True


def test_sell_over_owned_position_is_blocked_and_learnable() -> None:
    payload = {
        "action": "SELL",
        "symbol": "005930",
        "market": "kr_stock",
        "quantity": 3,
        "evidence_ids": ["ev-samsung-risk-001"],
    }
    tool_results = {
        **_complete_tool_results(),
        "get_positions": [
            {"symbol": "005930", "market": "kr_stock", "quantity": 1, "current_price": 70_000},
        ],
    }

    with pytest.raises(FinanceShadowValidationError) as exc_info:
        validate_finance_shadow_payload(payload, tool_results=tool_results)

    assert exc_info.value.code == "trade_exceeds_position"
    assert exc_info.value.details["owned_quantity"] == 1
    failure = build_finance_shadow_failure_record(exc_info.value, payload, tool_results=tool_results)
    assert failure["record_type"] == "raw_model_failure"
    assert failure["retrain_candidate"] is True


def test_small_trade_with_evidence_tools_and_risk_limit_marks_paper_order_intent() -> None:
    record = build_finance_shadow_record(
        {
            "action": "BUY",
            "symbol": "005930",
            "market": "kr_stock",
            "quantity": 2,
            "evidence_ids": ["ev-samsung-risk-001"],
            "reason": "risk-limited paper shadow decision",
        },
        tool_results=_complete_tool_results(),
    )

    assert record["action"] == "BUY"
    assert record["notional"] == 140_000
    assert record["within_risk_limit"] is True
    assert record["paper_trade_only"] is True
    assert record["would_submit_order"] is True
    assert record["quantity"] == 2
    assert record["price"] == 70_000
    assert set(record["tool_result_names"]) == {
        "get_balance",
        "get_positions",
        "get_quote",
        "get_ohlcv",
        "market_signal",
        "get_market_session",
        "get_risk_limit",
        "search_rag",
    }


def test_profit_guarantee_expression_is_blocked() -> None:
    with pytest.raises(FinanceShadowValidationError, match="profit_guarantee_expression"):
        validate_finance_shadow_payload(
            {
                "action": "HOLD",
                "symbol": "005930",
                "reason": "This is a guaranteed profit with no downside.",
            }
        )
