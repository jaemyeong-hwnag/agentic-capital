"""Shared test fixtures."""

import pytest

from agentic_capital.core.personality.models import EmotionState, PersonalityVector


@pytest.fixture
def default_personality() -> PersonalityVector:
    """A neutral personality vector (all 0.5)."""
    return PersonalityVector()


@pytest.fixture
def aggressive_personality() -> PersonalityVector:
    """An aggressive, risk-seeking personality."""
    return PersonalityVector(
        openness=0.8,
        conscientiousness=0.3,
        extraversion=0.9,
        agreeableness=0.2,
        neuroticism=0.7,
        honesty_humility=0.4,
        loss_aversion=0.2,
        risk_aversion_gains=0.2,
        risk_aversion_losses=0.3,
        probability_weighting=0.8,
    )


@pytest.fixture
def default_emotion() -> EmotionState:
    """A neutral emotion state."""
    return EmotionState()
