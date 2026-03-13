"""Emotion system — real-time VAD emotion updates."""

from agentic_capital.core.personality.models import EmotionState


def update_emotion_from_pnl(emotion: EmotionState, pnl_pct: float) -> EmotionState:
    """Update emotion state based on profit/loss percentage.

    Args:
        emotion: Current emotion state.
        pnl_pct: Profit/loss as percentage (e.g. 0.05 = +5%).

    Returns:
        Updated emotion state.
    """
    valence_delta = pnl_pct * 2.0  # Amplify PnL effect on mood
    arousal_delta = abs(pnl_pct) * 1.5  # Volatility increases arousal
    stress_delta = -pnl_pct * 0.5 if pnl_pct < 0 else -abs(pnl_pct) * 0.2
    confidence_delta = pnl_pct * 0.3

    return EmotionState(
        valence=max(-1.0, min(1.0, emotion.valence + valence_delta)),
        arousal=max(0.0, min(1.0, emotion.arousal + arousal_delta)),
        dominance=emotion.dominance,
        stress=max(0.0, min(1.0, emotion.stress + stress_delta)),
        confidence=max(0.0, min(1.0, emotion.confidence + confidence_delta)),
    )
