"""Agent factory — dynamically creates agents with personality vectors."""

from uuid import uuid4

import numpy as np

from agentic_capital.core.agents.base import AgentProfile
from agentic_capital.core.personality.models import PersonalityVector


def create_random_personality(seed: int | None = None) -> PersonalityVector:
    """Generate a random 15D personality vector.

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
