"""Cost-aware evaluation primitives.

The project optimizes for money, not activity. This module keeps the first
economic layer deliberately small: every LLM cycle gets an estimated AI cost,
and callers can attach realized net P&L when it is known.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agentic_capital.config import settings


class CostBasis(BaseModel):
    """Config values used to estimate one AI decision cycle."""

    fixed_cycle_krw: float = Field(default=0.0, ge=0.0)
    per_tool_call_krw: float = Field(default=0.0, ge=0.0)
    daily_op_cost_krw: float = Field(default=10_000.0, ge=0.0)

    def to_compact_dict(self) -> dict[str, float]:
        """Return a compact JSON-safe representation for DB snapshots."""
        return {
            "fixed_cycle_krw": self.fixed_cycle_krw,
            "per_tool_call_krw": self.per_tool_call_krw,
            "daily_op_cost_krw": self.daily_op_cost_krw,
        }


class CycleEconomics(BaseModel):
    """Economic snapshot for one agent cycle."""

    ai_cost_krw: float = Field(default=0.0, ge=0.0)
    net_pnl_krw: float | None = None
    decision_roi: float | None = None
    cost_basis: CostBasis

    def to_compact_dict(self) -> dict:
        """Return a compact JSON-safe representation for DB snapshots."""
        return {
            "ai_cost_krw": self.ai_cost_krw,
            "net_pnl_krw": self.net_pnl_krw,
            "decision_roi": self.decision_roi,
            "cost_basis": self.cost_basis.to_compact_dict(),
        }


def _default_basis() -> CostBasis:
    return CostBasis(
        fixed_cycle_krw=settings.ai_cost_per_cycle_krw,
        per_tool_call_krw=settings.ai_cost_per_tool_call_krw,
        daily_op_cost_krw=settings.ai_daily_op_cost_krw,
    )


def estimate_cycle_economics(
    *,
    tool_calls_count: int,
    net_pnl_krw: float | None = None,
    basis: CostBasis | None = None,
) -> CycleEconomics:
    """Estimate AI cost and decision ROI for a single agent cycle.

    `decision_roi` is only meaningful when realized net P&L is supplied. The
    recorder can still persist AI cost immediately, then later analysis can join
    trades/fills to compute richer realized economics.
    """
    effective_basis = basis or _default_basis()
    calls = max(0, tool_calls_count)
    ai_cost = effective_basis.fixed_cycle_krw + (effective_basis.per_tool_call_krw * calls)

    decision_roi = None
    if net_pnl_krw is not None and ai_cost > 0:
        decision_roi = net_pnl_krw / ai_cost

    return CycleEconomics(
        ai_cost_krw=ai_cost,
        net_pnl_krw=net_pnl_krw,
        decision_roi=decision_roi,
        cost_basis=effective_basis,
    )
