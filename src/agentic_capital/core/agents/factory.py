"""Agent factory — dynamically creates agents with personality vectors."""

from __future__ import annotations

from uuid import uuid4

import numpy as np

from agentic_capital.core.agents.base import AgentProfile, BaseAgent
from agentic_capital.core.personality.models import PersonalityVector


def create_random_personality(seed: int | None = None) -> PersonalityVector:
    """Generate a random 10D personality vector.

    Uses uniform distribution [0, 1] for each dimension.
    CEO can specify desired traits; otherwise fully random.
    """
    rng = np.random.default_rng(seed)
    values = rng.uniform(0.0, 1.0, size=10)

    return PersonalityVector(
        # Big5 (OCEAN)
        openness=float(values[0]),
        conscientiousness=float(values[1]),
        extraversion=float(values[2]),
        agreeableness=float(values[3]),
        neuroticism=float(values[4]),
        # HEXACO
        honesty_humility=float(values[5]),
        # Prospect Theory
        loss_aversion=float(values[6]),
        risk_aversion_gains=float(values[7]),
        risk_aversion_losses=float(values[8]),
        probability_weighting=float(values[9]),
    )


def create_agent_profile(
    name: str,
    philosophy: str = "",
    allocated_capital: float = 0.0,
) -> AgentProfile:
    """Create a new agent profile with a unique ID."""
    return AgentProfile(
        id=uuid4(),
        name=name,
        philosophy=philosophy,
        allocated_capital=allocated_capital,
    )


def create_agent(
    role: str,
    name: str,
    philosophy: str = "",
    allocated_capital: float = 0.0,
    seed: int | None = None,
    personality: PersonalityVector | None = None,
    *,
    llm: object | None = None,
    trading: object | None = None,
) -> BaseAgent:
    """Create a typed agent based on role.

    Args:
        role: Agent role — 'ceo', 'analyst', 'trader', or any custom role.
        name: Agent name.
        philosophy: Investment/management philosophy.
        allocated_capital: Initial capital allocation.
        seed: Random seed for personality generation.
        personality: Pre-defined personality (overrides seed).
        llm: LLMPort instance (required for all roles).
        trading: TradingPort instance (required for trader).

    Returns:
        A concrete BaseAgent subclass instance.
    """
    from agentic_capital.core.agents.analyst import AnalystAgent
    from agentic_capital.core.agents.ceo import CEOAgent
    from agentic_capital.core.agents.trader import TraderAgent
    from agentic_capital.ports.llm import LLMPort
    from agentic_capital.ports.trading import TradingPort

    profile = create_agent_profile(name, philosophy, allocated_capital)
    p = personality or create_random_personality(seed)

    if not isinstance(llm, LLMPort):
        msg = f"llm must be a LLMPort instance, got {type(llm)}"
        raise TypeError(msg)

    role_lower = role.lower()
    if role_lower == "ceo":
        return CEOAgent(profile=profile, personality=p, llm=llm)
    elif role_lower == "trader":
        if not isinstance(trading, TradingPort):
            msg = f"trading must be a TradingPort instance for trader, got {type(trading)}"
            raise TypeError(msg)
        return TraderAgent(profile=profile, personality=p, llm=llm, trading=trading)
    else:
        # Any other role (analyst, CIO, quant strategist, risk manager, etc.)
        # defaults to AnalystAgent — AI agents create any role they want
        return AnalystAgent(profile=profile, personality=p, llm=llm)
