"""Personality drift — personality evolves based on experience."""

from pydantic import BaseModel

from agentic_capital.core.personality.models import PersonalityVector


class DriftEvent(BaseModel):
    """Record of a personality parameter change."""

    parameter: str
    old_value: float
    new_value: float
    trigger_event: str
    reasoning: str


def apply_drift(
    personality: PersonalityVector,
    parameter: str,
    delta: float,
    trigger_event: str,
    reasoning: str,
) -> tuple[PersonalityVector, DriftEvent]:
    """Apply a personality drift to a specific parameter.

    Args:
        personality: Current personality vector.
        parameter: Which dimension to change (e.g. "openness").
        delta: Amount to change (can be negative).
        trigger_event: What caused the drift (e.g. "big_loss").
        reasoning: AI-generated explanation.

    Returns:
        Updated personality vector and drift event record.
    """
    old_value = getattr(personality, parameter)
    new_value = max(0.0, min(1.0, old_value + delta))

    updated = personality.model_copy(update={parameter: new_value})
    event = DriftEvent(
        parameter=parameter,
        old_value=old_value,
        new_value=new_value,
        trigger_event=trigger_event,
        reasoning=reasoning,
    )
    return updated, event
