"""Agent workflow — free tool-use (ReAct) loop.

System provides tools. Agent decides everything: what to check, when to trade,
what order, how many times. No fixed pipeline. No forced steps.

The only constraint: capital. The only goal: make money.
"""

from __future__ import annotations

from typing import Any

import structlog
from langgraph.prebuilt import create_react_agent  # noqa: F401 — imported at module level for testability

from agentic_capital.config import settings
from agentic_capital.core.agents.base import BaseAgent
from agentic_capital.core.tools.data_query import build_agent_tools
from agentic_capital.graph.nodes import record_cycle

logger = structlog.get_logger()

_langchain_llm = None


def _get_langchain_llm():
    """Lazy-init LangChain-compatible Gemini LLM (shared across agents)."""
    global _langchain_llm
    if _langchain_llm is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _langchain_llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.gemini_api_key,
            temperature=0.7,
        )
    return _langchain_llm


def _build_system_prompt(agent: BaseAgent) -> str:
    """Build compact AI-optimized system prompt.

    ~75% token reduction vs verbose format.
    Uses XML tags (Claude-native), Big5 abbreviations (LLM-universal),
    and LEGEND schema defined once for implicit reuse.
    """
    from agentic_capital.formats.compact import LEGEND, MANDATE, psych

    agent_class = type(agent).__name__
    if "CEO" in agent_class:
        role = "CEO"
        role_ctx = "act:hire|fire|restructure|strategy|trade|send_message"
    elif "Analyst" in agent_class:
        role = "analyst"
        role_ctx = "act:analyze→signal→send_message(traders)"
    else:
        role = "trader"
        role_ctx = "act:assess→decide→submit_order"

    return (
        f"{LEGEND}\n"
        f"<agent name=\"{agent.name}\" role=\"{role}\">\n"
        f"<phi>{agent.profile.philosophy}</phi>\n"
        f"{psych(agent.personality, agent.emotion)}\n"
        f"</agent>\n"
        f"{MANDATE}\n"
        f"{role_ctx}"
    )


async def run_agent_cycle(
    agent: BaseAgent,
    cycle_number: int,
    *,
    trading: Any = None,
    symbols: list[str] | None = None,
    open_markets: list[str] | None = None,
    recorder: Any = None,
) -> dict:
    """Run one autonomous cycle for an agent using ReAct tool-use loop.

    The agent receives all tools and decides freely what to do.
    No workflow, no forced steps.

    Returns:
        dict with 'decisions', 'messages', 'errors' for the engine to process.
    """
    from langchain_core.messages import HumanMessage

    tools, decisions_sink, messages_sink = build_agent_tools(
        trading=trading,
        recorder=recorder,
        agent_id=str(agent.agent_id),
        agent_name=agent.name,
        agent_memory=getattr(agent, "_memory", None),
    )

    system_prompt = _build_system_prompt(agent)
    llm = _get_langchain_llm()

    react_agent = create_react_agent(llm, tools, prompt=system_prompt)

    if open_markets:
        market_status = f"Currently open markets: {', '.join(open_markets)}."
    else:
        market_status = "All major markets are currently closed."

    cycle_trigger = f"C{cycle_number}|{market_status}|act_now"

    logger.info("agent_cycle_start", agent=agent.name, cycle=cycle_number)

    errors: list[str] = []
    result_messages = []

    try:
        result = await react_agent.ainvoke(
            {"messages": [HumanMessage(content=cycle_trigger)]},
            config={"recursion_limit": 50},  # type: ignore[arg-type]
        )
        result_messages = result.get("messages", [])
    except Exception as e:
        errors.append(str(e))
        logger.exception("agent_react_cycle_failed", agent=agent.name, cycle=cycle_number)

    # Extract any decisions from LLM output (hire/fire/org actions from text)
    org_decisions = _extract_org_decisions(result_messages)

    all_decisions = decisions_sink + org_decisions

    # Record everything to DB
    await record_cycle(
        agent=agent,
        cycle_number=cycle_number,
        decisions=all_decisions,
        messages=messages_sink,
        recorder=recorder,
    )

    logger.info(
        "agent_cycle_complete",
        agent=agent.name,
        cycle=cycle_number,
        decisions=len(all_decisions),
        tool_calls=len(decisions_sink),
        errors=len(errors),
    )

    return {
        "agent_id": str(agent.agent_id),
        "agent_name": agent.name,
        "cycle_number": cycle_number,
        "decisions": all_decisions,
        "messages_to_send": messages_sink,
        "errors": errors,
        "emotion": {
            "valence": agent.emotion.valence,
            "arousal": agent.emotion.arousal,
            "dominance": agent.emotion.dominance,
            "stress": agent.emotion.stress,
            "confidence": agent.emotion.confidence,
        },
    }


def _extract_org_decisions(messages: list) -> list[dict]:
    """Extract hire/fire/create_role decisions from agent messages.

    CEOs may output org decisions in their final text response.
    We parse these from the last AIMessage content.
    """
    import json
    import re

    for msg in reversed(messages):
        # Check for AIMessage with text content
        content = getattr(msg, "content", None)
        if not content or not isinstance(content, str):
            continue

        # Try JSON block
        json_match = re.search(r"```json\s*(\[.*?\]|\{.*?\})\s*```", content, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(1))
                if isinstance(parsed, list):
                    return [d for d in parsed if isinstance(d, dict) and "type" in d]
                if isinstance(parsed, dict) and "type" in parsed:
                    return [parsed]
            except (json.JSONDecodeError, ValueError):
                pass

        # Try bare JSON array/object
        for pattern in [r"(\[[\s\S]*?\])", r"(\{[\s\S]*?\})"]:
            match = re.search(pattern, content)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                    if isinstance(parsed, list):
                        org_types = {"hire", "fire", "create_role", "abolish_role"}
                        org_decisions = [d for d in parsed if isinstance(d, dict) and d.get("type") in org_types]
                        if org_decisions:
                            return org_decisions
                except (json.JSONDecodeError, ValueError):
                    pass

    return []
