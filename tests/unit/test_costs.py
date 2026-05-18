"""Tests for cost-aware evaluation utilities."""

from agentic_capital.core.evaluation.costs import CostBasis, estimate_cycle_economics


def test_estimate_cycle_economics_counts_fixed_and_tool_costs() -> None:
    economics = estimate_cycle_economics(
        tool_calls_count=3,
        basis=CostBasis(
            fixed_cycle_krw=100.0,
            per_tool_call_krw=25.0,
            daily_op_cost_krw=10_000.0,
        ),
    )

    assert economics.ai_cost_krw == 175.0
    assert economics.net_pnl_krw is None
    assert economics.decision_roi is None
    assert economics.to_compact_dict()["cost_basis"]["daily_op_cost_krw"] == 10_000.0


def test_estimate_cycle_economics_computes_decision_roi() -> None:
    economics = estimate_cycle_economics(
        tool_calls_count=2,
        net_pnl_krw=500.0,
        basis=CostBasis(fixed_cycle_krw=100.0, per_tool_call_krw=50.0),
    )

    assert economics.ai_cost_krw == 200.0
    assert economics.decision_roi == 2.5


def test_estimate_cycle_economics_clamps_negative_tool_count() -> None:
    economics = estimate_cycle_economics(
        tool_calls_count=-5,
        basis=CostBasis(fixed_cycle_krw=100.0, per_tool_call_krw=50.0),
    )

    assert economics.ai_cost_krw == 100.0
