"""LangGraph state definitions for agent workflows.

The state carries context that agents can read and write.
System records everything — agents decide what to do with it.
"""

from __future__ import annotations

from typing import Annotated, TypedDict
from uuid import UUID

from langgraph.graph import add_messages


class AgentWorkflowState(TypedDict, total=False):
    """State for a single agent's decision cycle.

    All fields are optional — agents decide what to populate.
    System provides tools; agents use them autonomously.
    """

    # Agent identity
    agent_id: str
    agent_name: str
    agent_role: str  # ceo, analyst, trader, or any role CEO creates

    # Current cycle
    cycle_number: int

    # Data the agent has gathered (agent decides what to query)
    market_data: list[dict]
    balance: dict
    positions: list[dict]
    agent_roster: list[dict]  # For CEO: current agents and their status
    company_state: dict
    messages_received: list[dict]  # LACP messages from other agents

    # Agent's decisions this cycle
    decisions: list[dict]  # Trading decisions, HR decisions, signals, etc.
    messages_to_send: list[dict]  # LACP messages to publish

    # Reflection
    reflection: str
    personality_drifts: list[dict]

    # Emotion after this cycle
    emotion: dict

    # Error tracking
    errors: list[str]


class SimulationState(TypedDict, total=False):
    """Top-level simulation state across all agents.

    The simulation orchestrator uses this to coordinate cycles.
    Individual agent workflows run independently.
    """

    # Simulation metadata
    simulation_id: str
    cycle_number: int
    seed: int

    # Agents in the simulation
    agents: list[dict]  # [{id, name, role, personality, emotion, capital}, ...]

    # Cycle results (accumulated)
    cycle_results: list[dict]  # Results from each agent's cycle

    # Company-wide metrics (recorded, not enforced)
    total_capital: float
    available_cash: float
