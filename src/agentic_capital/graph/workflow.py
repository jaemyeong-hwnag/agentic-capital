"""LangGraph workflow — agent orchestration graph.

Each agent runs through: gather_data → think → reflect → record.
The workflow is the same for all roles — what differs is the agent's
autonomous behavior within each node.

System provides the graph structure. Agents provide the intelligence.
"""

from __future__ import annotations

from functools import partial
from typing import Any

import structlog
from langgraph.graph import END, StateGraph

from agentic_capital.core.agents.base import BaseAgent
from agentic_capital.graph.nodes import gather_data, think, reflect, record
from agentic_capital.graph.state import AgentWorkflowState

logger = structlog.get_logger()


def build_agent_workflow(
    agent: BaseAgent,
    *,
    trading: Any = None,
    market_data: Any = None,
    symbols: list[str] | None = None,
    recorder: Any = None,
) -> StateGraph:
    """Build a LangGraph workflow for a single agent.

    The graph structure is: gather_data → think → reflect → record → END

    All agents follow the same graph. The agent's role and personality
    determine what happens inside each node — the system doesn't restrict
    or guide behavior. System only provides tools and records results.

    Args:
        agent: The agent to run (CEO, Analyst, Trader, or any future role).
        trading: TradingPort adapter.
        market_data: MarketDataPort adapter.
        symbols: Available symbols (agent decides which to look at).
        recorder: SimulationRecorder for DB persistence.

    Returns:
        A compiled LangGraph StateGraph.
    """
    deps = {
        "trading": trading,
        "market_data": market_data,
        "symbols": symbols or [],
        "recorder": recorder,
    }

    # Create node functions bound to this agent and its dependencies
    async def _gather(state: AgentWorkflowState) -> AgentWorkflowState:
        return await gather_data(state, agent, **deps)

    async def _think(state: AgentWorkflowState) -> AgentWorkflowState:
        return await think(state, agent, **deps)

    async def _reflect(state: AgentWorkflowState) -> AgentWorkflowState:
        return await reflect(state, agent, **deps)

    async def _record(state: AgentWorkflowState) -> AgentWorkflowState:
        return await record(state, agent, **deps)

    # Build the graph
    graph = StateGraph(AgentWorkflowState)

    graph.add_node("gather_data", _gather)
    graph.add_node("think", _think)
    graph.add_node("reflect", _reflect)
    graph.add_node("record", _record)

    # Linear flow: gather → think → reflect → record → END
    graph.set_entry_point("gather_data")
    graph.add_edge("gather_data", "think")
    graph.add_edge("think", "reflect")
    graph.add_edge("reflect", "record")
    graph.add_edge("record", END)

    return graph


async def run_agent_cycle(
    agent: BaseAgent,
    cycle_number: int,
    *,
    trading: Any = None,
    market_data: Any = None,
    symbols: list[str] | None = None,
    recorder: Any = None,
) -> AgentWorkflowState:
    """Run one complete cycle for an agent using LangGraph.

    Returns the final state after the cycle completes.
    """
    graph = build_agent_workflow(
        agent,
        trading=trading,
        market_data=market_data,
        symbols=symbols,
        recorder=recorder,
    )

    compiled = graph.compile()

    initial_state: AgentWorkflowState = {
        "agent_id": str(agent.agent_id),
        "agent_name": agent.name,
        "agent_role": agent.profile.role_id if hasattr(agent.profile, "role_id") else "",
        "cycle_number": cycle_number,
        "market_data": [],
        "balance": {},
        "positions": [],
        "decisions": [],
        "messages_to_send": [],
        "errors": [],
    }

    logger.info("agent_cycle_start", agent=agent.name, cycle=cycle_number)

    result = await compiled.ainvoke(initial_state)

    logger.info(
        "agent_cycle_complete",
        agent=agent.name,
        cycle=cycle_number,
        decisions=len(result.get("decisions", [])),
        errors=len(result.get("errors", [])),
    )

    return result
