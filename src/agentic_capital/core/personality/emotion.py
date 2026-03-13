"""Emotion system — VAD emotion model.

Emotion utility functions are available as TOOLS agents can optionally use.
The system does NOT enforce any emotion changes — agents decide autonomously
whether and how to update their emotional state.
"""

from agentic_capital.core.personality.models import EmotionState


def create_emotion(
    valence: float = 0.0,
    arousal: float = 0.5,
    dominance: float = 0.5,
    stress: float = 0.3,
    confidence: float = 0.5,
) -> EmotionState:
    """Create a new emotion state with clamped values.

    This is a utility — agents can use it if they choose to.
    Not system-enforced.
    """
    return EmotionState(
        valence=max(-1.0, min(1.0, valence)),
        arousal=max(0.0, min(1.0, arousal)),
        dominance=max(0.0, min(1.0, dominance)),
        stress=max(0.0, min(1.0, stress)),
        confidence=max(0.0, min(1.0, confidence)),
    )
