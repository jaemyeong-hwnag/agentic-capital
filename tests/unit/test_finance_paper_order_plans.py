"""Unit tests for local finance paper order planning."""

from unittest.mock import patch

from agentic_capital.graph.workflow import (
    _finance_cycle_symbol_market,
    _finance_loop_probe_order_plan,
    _finance_paper_order_plan,
    _finance_wait_probe_order_plan,
)


def _tool_results(*, positions=None):
    return {
        "get_market_session": {"state": "regular"},
        "get_quote": {"price": 185.0, "market": "us_stock"},
        "get_balance": {"available": 10_000.0},
        "get_risk_limit": {"max_order_value": 1_000.0},
        "get_positions": positions or [],
    }


def test_finance_paper_order_plan_allows_overseas_buy_with_local_paper_price():
    with (
        patch("agentic_capital.graph.workflow.settings.kis_is_paper", True),
        patch("agentic_capital.graph.workflow.settings.futures_live_orders_enabled", False),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_order_execution_enabled", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_risk_per_trade_pct", 0.2),
    ):
        plan = _finance_paper_order_plan(
            record={
                "paper_trade_only": True,
                "within_risk_limit": True,
                "would_submit_order": True,
                "market": "us_stock",
                "symbol": "AAPL",
            },
            decision={"action": "BUY", "symbol": "AAPL", "market": "us_stock", "exchange": "NASD"},
            tool_results=_tool_results(),
            primary_symbol="AAPL",
            primary_market="us_stock",
            open_markets=["NASDAQ"],
            capital_limit=10_000.0,
        )

    assert plan is not None
    assert plan["market"] == "us_stock"
    assert plan["price"] == 185.0
    assert plan["exchange"] == "NASD"
    assert plan["quantity"] == 1


def test_finance_paper_order_plan_allows_overseas_buy_during_premarket():
    with (
        patch("agentic_capital.graph.workflow.settings.kis_is_paper", True),
        patch("agentic_capital.graph.workflow.settings.futures_live_orders_enabled", False),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_order_execution_enabled", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_risk_per_trade_pct", 0.2),
    ):
        plan = _finance_paper_order_plan(
            record={
                "paper_trade_only": True,
                "within_risk_limit": True,
                "would_submit_order": True,
                "market": "us_stock",
                "symbol": "AAPL",
            },
            decision={"action": "BUY", "symbol": "AAPL", "market": "us_stock", "exchange": "NASD"},
            tool_results={
                **_tool_results(),
                "get_market_session": {"exchange": "NASDAQ", "state": "pre", "session": "pre", "is_open": True, "regular_session": False},
            },
            primary_symbol="AAPL",
            primary_market="us_stock",
            open_markets=["NASDAQ_PRE"],
            capital_limit=10_000.0,
        )

    assert plan is not None
    assert plan["market"] == "us_stock"
    assert plan["price"] == 185.0


def test_finance_paper_order_plan_allows_overseas_sell_when_position_owned():
    with (
        patch("agentic_capital.graph.workflow.settings.kis_is_paper", True),
        patch("agentic_capital.graph.workflow.settings.futures_live_orders_enabled", False),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_order_execution_enabled", True),
    ):
        plan = _finance_paper_order_plan(
            record={
                "paper_trade_only": True,
                "within_risk_limit": True,
                "would_submit_order": True,
                "market": "us_stock",
                "symbol": "AAPL",
            },
            decision={"action": "SELL", "symbol": "AAPL", "market": "us_stock", "quantity": 3},
            tool_results=_tool_results(positions=[
                {"symbol": "AAPL", "market": "us_stock", "quantity": 2}
            ]),
            primary_symbol="AAPL",
            primary_market="us_stock",
            open_markets=["NASDAQ"],
            capital_limit=10_000.0,
        )

    assert plan is not None
    assert plan["action"] == "SELL"
    assert plan["quantity"] == 2


def test_finance_paper_order_plan_allows_call_option_buy_without_quote_price():
    with (
        patch("agentic_capital.graph.workflow.settings.kis_is_paper", True),
        patch("agentic_capital.graph.workflow.settings.futures_live_orders_enabled", False),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_order_execution_enabled", True),
    ):
        plan = _finance_paper_order_plan(
            record={
                "paper_trade_only": True,
                "within_risk_limit": True,
                "would_submit_order": True,
                "market": "kr_options",
                "symbol": "K200_CALL_ATM",
                "option_type": "call",
            },
            decision={"action": "BUY", "symbol": "K200_CALL_ATM", "market": "kr_options"},
            tool_results={**_tool_results(), "get_quote": {"price": 0.0}},
            primary_symbol="K200_CALL_ATM",
            primary_market="kr_options",
            open_markets=["NIGHT"],
            capital_limit=10_000.0,
        )

    assert plan is not None
    assert plan["market"] == "kr_options"
    assert plan["option_type"] == "call"
    assert plan["position_effect"] == "open"
    assert plan["quantity"] == 1
    assert plan["price"] is None


def test_finance_paper_order_plan_allows_call_option_buy_with_explicit_night_session():
    with (
        patch("agentic_capital.graph.workflow.settings.kis_is_paper", True),
        patch("agentic_capital.graph.workflow.settings.futures_live_orders_enabled", False),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_order_execution_enabled", True),
    ):
        plan = _finance_paper_order_plan(
            record={
                "paper_trade_only": True,
                "within_risk_limit": True,
                "would_submit_order": True,
                "market": "kr_options",
                "symbol": "K200_CALL_ATM",
                "option_type": "call",
            },
            decision={"action": "BUY", "symbol": "K200_CALL_ATM", "market": "kr_options"},
            tool_results={
                **_tool_results(),
                "get_market_session": {"exchange": "NIGHT", "state": "night", "session": "night", "is_open": True, "regular_session": False},
                "get_quote": {"price": 0.0, "market": "kr_options"},
            },
            primary_symbol="K200_CALL_ATM",
            primary_market="kr_options",
            open_markets=[],
            capital_limit=10_000.0,
        )

    assert plan is not None
    assert plan["market"] == "kr_options"
    assert plan["option_type"] == "call"


def test_finance_paper_order_plan_rejects_put_option():
    with (
        patch("agentic_capital.graph.workflow.settings.kis_is_paper", True),
        patch("agentic_capital.graph.workflow.settings.futures_live_orders_enabled", False),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_order_execution_enabled", True),
    ):
        plan = _finance_paper_order_plan(
            record={
                "paper_trade_only": True,
                "within_risk_limit": True,
                "would_submit_order": True,
                "market": "kr_options",
                "symbol": "K200_PUT_ATM",
                "option_type": "put",
            },
            decision={"action": "BUY", "symbol": "K200_PUT_ATM", "market": "kr_options"},
            tool_results={**_tool_results(), "get_quote": {"price": 0.0}},
            primary_symbol="K200_PUT_ATM",
            primary_market="kr_options",
            open_markets=["NIGHT"],
            capital_limit=10_000.0,
        )

    assert plan is None


def test_finance_loop_probe_recovers_call_tool_shadow_call_option():
    with (
        patch("agentic_capital.graph.workflow.settings.kis_is_paper", True),
        patch("agentic_capital.graph.workflow.settings.futures_live_orders_enabled", False),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_order_execution_enabled", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_probe_on_model_loop", True),
    ):
        plan = _finance_loop_probe_order_plan(
            record={
                "record_type": "finance_paper_shadow_decision",
                "action": "CALL_TOOL",
                "paper_trade_only": True,
                "market": "kr_options",
                "symbol": "K200_CALL_ATM",
                "option_type": "call",
            },
            tool_results={
                **_tool_results(),
                "get_market_session": {"state": "closed", "market": "kr_options"},
                "get_quote": {"price": 0.0},
            },
            primary_symbol="K200_CALL_ATM",
            primary_market="kr_options",
            open_markets=["NIGHT"],
            capital_limit=10_000.0,
            evidence_ids=["source_reference.md"],
            risk_flags=[],
        )

    assert plan is not None
    assert plan["action"] == "BUY"
    assert plan["market"] == "kr_options"
    assert plan["option_type"] == "call"
    assert plan["position_effect"] == "open"


def test_finance_wait_probe_uses_primary_market_when_record_omits_market():
    with (
        patch("agentic_capital.graph.workflow.settings.kis_is_paper", True),
        patch("agentic_capital.graph.workflow.settings.futures_live_orders_enabled", False),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_order_execution_enabled", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_probe_on_model_loop", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_risk_per_trade_pct", 0.2),
    ):
        plan = _finance_wait_probe_order_plan(
            record={
                "record_type": "finance_paper_shadow_decision",
                "action": "WAIT",
                "paper_trade_only": True,
                "would_submit_order": False,
                "within_risk_limit": True,
                "symbol": "AAPL",
            },
            tool_results=_tool_results(),
            primary_symbol="AAPL",
            primary_market="us_stock",
            open_markets=["NASDAQ_PRE"],
            capital_limit=10_000.0,
            evidence_ids=["source_reference.md"],
            risk_flags=[],
        )

    assert plan is not None
    assert plan["symbol"] == "AAPL"
    assert plan["market"] == "us_stock"
    assert plan["price"] == 185.0
    assert plan["quantity"] == 1


def test_finance_wait_probe_blocks_observe_insufficient_edge_without_confidence():
    with (
        patch("agentic_capital.graph.workflow.settings.kis_is_paper", True),
        patch("agentic_capital.graph.workflow.settings.futures_live_orders_enabled", False),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_order_execution_enabled", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_probe_on_model_loop", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_risk_per_trade_pct", 0.1),
    ):
        plan = _finance_wait_probe_order_plan(
            record={
                "record_type": "finance_paper_shadow_decision",
                "action": "OBSERVE",
                "paper_trade_only": True,
                "would_submit_order": False,
                "within_risk_limit": True,
                "symbol": "005930",
                "market": "kr_stock",
                "confidence": 0.0,
                "no_trade_reason": "insufficient_edge",
            },
            tool_results={
                **_tool_results(),
                "get_quote": {"symbol": "005930", "price": 350500, "market": "kr_stock"},
                "get_balance": {"available": 5_000_000.0},
                "get_risk_limit": {"max_order_value": 5_000_000.0},
            },
            primary_symbol="005930",
            primary_market="kr_stock",
            open_markets=["KRX"],
            capital_limit=5_000_000.0,
            evidence_ids=[],
            risk_flags=[],
        )

    assert plan is None


def test_finance_wait_probe_recovers_observe_performance_candidate():
    with (
        patch("agentic_capital.graph.workflow.settings.kis_is_paper", True),
        patch("agentic_capital.graph.workflow.settings.futures_live_orders_enabled", False),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_order_execution_enabled", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_probe_on_model_loop", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_risk_per_trade_pct", 0.1),
    ):
        plan = _finance_wait_probe_order_plan(
            record={
                "record_type": "finance_paper_shadow_decision",
                "action": "OBSERVE",
                "paper_trade_only": True,
                "would_submit_order": False,
                "within_risk_limit": True,
                "symbol": "005930",
                "market": "kr_stock",
                "confidence": 0.2,
                "no_trade_reason": "paper_scout_candidate",
            },
            tool_results={
                **_tool_results(),
                "get_quote": {"symbol": "005930", "price": 350500, "market": "kr_stock"},
                "get_balance": {"available": 5_000_000.0},
                "get_risk_limit": {"max_order_value": 5_000_000.0},
            },
            primary_symbol="005930",
            primary_market="kr_stock",
            open_markets=["KRX"],
            capital_limit=5_000_000.0,
            evidence_ids=["runtime-tool-evidence"],
            risk_flags=[],
        )

    assert plan is not None
    assert plan["action"] == "BUY"
    assert plan["symbol"] == "005930"
    assert plan["market"] == "kr_stock"
    assert plan["quantity"] == 1
    assert "OBSERVE" in plan["reason"]


def test_finance_wait_probe_uses_complete_runtime_tools_as_evidence():
    with (
        patch("agentic_capital.graph.workflow.settings.kis_is_paper", True),
        patch("agentic_capital.graph.workflow.settings.futures_live_orders_enabled", False),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_order_execution_enabled", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_probe_on_model_loop", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_risk_per_trade_pct", 0.1),
    ):
        plan = _finance_wait_probe_order_plan(
            record={
                "record_type": "finance_paper_shadow_decision",
                "action": "OBSERVE",
                "paper_trade_only": True,
                "would_submit_order": False,
                "within_risk_limit": True,
                "symbol": "005930",
                "market": "kr_stock",
                "confidence": 0.3,
                "no_trade_reason": "paper_scout_candidate",
            },
            tool_results={
                "get_market_session": {"state": "regular", "market": "kr_stock"},
                "get_quote": {"symbol": "005930", "price": 351000, "market": "kr_stock"},
                "get_balance": {"available": 5_000_000.0},
                "get_risk_limit": {"max_order_value": 5_000_000.0},
                "get_positions": [],
            },
            primary_symbol="005930",
            primary_market="kr_stock",
            open_markets=["KRX"],
            capital_limit=5_000_000.0,
            evidence_ids=[],
            risk_flags=[],
        )

    assert plan is not None
    assert plan["action"] == "BUY"
    assert plan["quantity"] == 1


def test_finance_wait_probe_blocks_same_price_rebuy_churn():
    with (
        patch("agentic_capital.graph.workflow.settings.kis_is_paper", True),
        patch("agentic_capital.graph.workflow.settings.futures_live_orders_enabled", False),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_order_execution_enabled", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_probe_on_model_loop", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_risk_per_trade_pct", 0.2),
    ):
        plan = _finance_wait_probe_order_plan(
            record={
                "record_type": "finance_paper_shadow_decision",
                "action": "OBSERVE",
                "paper_trade_only": True,
                "would_submit_order": False,
                "within_risk_limit": True,
                "symbol": "AAPL",
                "market": "us_stock",
                "confidence": 0.4,
                "no_trade_reason": "paper_scout_candidate",
            },
            tool_results={
                **_tool_results(),
                "get_fills": [
                    {"symbol": "AAPL", "side": "sell", "filled_price": 185.0, "quantity": 1},
                ],
            },
            primary_symbol="AAPL",
            primary_market="us_stock",
            open_markets=["NASDAQ"],
            capital_limit=10_000.0,
            evidence_ids=["source_reference.md"],
            risk_flags=[],
        )

    assert plan is None


def test_finance_wait_probe_recovers_hold_call_option():
    with (
        patch("agentic_capital.graph.workflow.settings.kis_is_paper", True),
        patch("agentic_capital.graph.workflow.settings.futures_live_orders_enabled", False),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_order_execution_enabled", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_probe_on_model_loop", True),
    ):
        plan = _finance_wait_probe_order_plan(
            record={
                "record_type": "finance_paper_shadow_decision",
                "action": "HOLD",
                "paper_trade_only": True,
                "would_submit_order": False,
                "within_risk_limit": True,
                "market": "kr_options",
                "symbol": "K200_CALL_ATM",
                "option_type": "call",
                "confidence": 0.2,
                "no_trade_reason": "paper_scout_candidate",
            },
            tool_results={**_tool_results(), "get_quote": {"price": 0.0}},
            primary_symbol="K200_CALL_ATM",
            primary_market="kr_options",
            open_markets=["KRX"],
            capital_limit=10_000.0,
            evidence_ids=["source_reference.md"],
            risk_flags=[],
        )

    assert plan is not None
    assert plan["action"] == "BUY"
    assert plan["market"] == "kr_options"
    assert plan["option_type"] == "call"
    assert plan["quantity"] == 1


def test_finance_wait_probe_sells_one_when_current_symbol_is_owned():
    with (
        patch("agentic_capital.graph.workflow.settings.kis_is_paper", True),
        patch("agentic_capital.graph.workflow.settings.futures_live_orders_enabled", False),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_order_execution_enabled", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_probe_on_model_loop", True),
    ):
        plan = _finance_wait_probe_order_plan(
            record={
                "record_type": "finance_paper_shadow_decision",
                "action": "WAIT",
                "paper_trade_only": True,
                "would_submit_order": False,
                "within_risk_limit": True,
                "symbol": "AAPL",
                "confidence": 0.2,
                "no_trade_reason": "paper_scout_candidate",
            },
            tool_results=_tool_results(positions=[
                {"symbol": "AAPL", "market": "us_stock", "quantity": 159, "avg_price": 180.0}
            ]),
            primary_symbol="AAPL",
            primary_market="us_stock",
            open_markets=["NASDAQ_PRE"],
            capital_limit=10_000.0,
            evidence_ids=["source_reference.md"],
            risk_flags=[],
        )

    assert plan is not None
    assert plan["action"] == "SELL"
    assert plan["market"] == "us_stock"
    assert plan["quantity"] == 1
    assert plan["price"] == 185.0


def test_finance_wait_probe_blocks_sell_when_fees_exceed_edge():
    with (
        patch("agentic_capital.graph.workflow.settings.kis_is_paper", True),
        patch("agentic_capital.graph.workflow.settings.futures_live_orders_enabled", False),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_order_execution_enabled", True),
        patch("agentic_capital.graph.workflow.settings.local_finance_paper_probe_on_model_loop", True),
    ):
        plan = _finance_wait_probe_order_plan(
            record={
                "record_type": "finance_paper_shadow_decision",
                "action": "OBSERVE",
                "paper_trade_only": True,
                "would_submit_order": False,
                "within_risk_limit": True,
                "symbol": "AAPL",
                "confidence": 0.2,
                "no_trade_reason": "paper_scout_candidate",
            },
            tool_results=_tool_results(positions=[
                {"symbol": "AAPL", "market": "us_stock", "quantity": 1, "avg_price": 185.0}
            ]),
            primary_symbol="AAPL",
            primary_market="us_stock",
            open_markets=["NASDAQ_PRE"],
            capital_limit=10_000.0,
            evidence_ids=["source_reference.md"],
            risk_flags=[],
        )

    assert plan is None


def test_finance_cycle_symbol_market_rotates_configured_multi_market_universe():
    with (
        patch("agentic_capital.graph.workflow.settings.local_finance_default_symbols", "005930,us_stock:AAPL"),
        patch("agentic_capital.graph.workflow.settings.local_finance_default_market", "us_stock"),
    ):
        first = _finance_cycle_symbol_market(1, None)
        second = _finance_cycle_symbol_market(2, None)

    assert first == ("005930", "kr_stock", ["005930", "us_stock:AAPL"])
    assert second == ("AAPL", "us_stock", ["005930", "us_stock:AAPL"])
