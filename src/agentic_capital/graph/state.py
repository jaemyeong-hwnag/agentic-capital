"""State definitions — result schema from agent cycles.

Agents use the ReAct pattern (free tool-use loop) — no fixed workflow state.
This module defines the output schema returned after each cycle completes.
"""

from __future__ import annotations

from typing import TypedDict


class AgentCycleResult(TypedDict, total=False):
    """Result returned by run_agent_cycle() after an agent completes a cycle.

    This is output-only — not a workflow state. The agent drives the loop
    internally via tool calls. This captures what happened for the engine.
    """

    agent_id: str
    agent_name: str
    cycle_number: int

    # Decisions made this cycle (trades submitted, org actions, etc.)
    decisions: list[dict]

    # Messages sent to other agents
    messages_to_send: list[dict]

    # Any errors during the cycle
    errors: list[str]


# Alias for backward compatibility with code that imports AgentWorkflowState
AgentWorkflowState = AgentCycleResult


class SimulationState(TypedDict, total=False):
    """Top-level simulation state across all agents (used by engine)."""

    simulation_id: str
    cycle_number: int
    seed: int

    agents: list[dict]
    cycle_results: list[dict]

    total_capital: float
    available_cash: float
