"""Personality and emotion models — 15D personality vector + VAD emotion."""

from pydantic import BaseModel, Field


class PersonalityVector(BaseModel):
    """15D personality vector that drives agent behavior.

    All values normalized to [0, 1].
    Personality drifts over time based on experience.
    """

    # Big5 (OCEAN) — 5D
    openness: float = Field(default=0.5, ge=0.0, le=1.0)
    conscientiousness: float = Field(default=0.5, ge=0.0, le=1.0)
    extraversion: float = Field(default=0.5, ge=0.0, le=1.0)
    agreeableness: float = Field(default=0.5, ge=0.0, le=1.0)
    neuroticism: float = Field(default=0.5, ge=0.0, le=1.0)

    # HEXACO — 1D
    honesty_humility: float = Field(default=0.5, ge=0.0, le=1.0)

    # Prospect Theory — 4D
    loss_aversion: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_aversion_gains: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_aversion_losses: float = Field(default=0.5, ge=0.0, le=1.0)
    probability_weighting: float = Field(default=0.5, ge=0.0, le=1.0)

    def to_list(self) -> list[float]:
        """Convert to flat list for embedding/storage."""
        return [
            self.openness,
            self.conscientiousness,
            self.extraversion,
            self.agreeableness,
            self.neuroticism,
            self.honesty_humility,
            self.loss_aversion,
            self.risk_aversion_gains,
            self.risk_aversion_losses,
            self.probability_weighting,
        ]

    @classmethod
    def from_list(cls, values: list[float]) -> "PersonalityVector":
        """Create from flat list."""
        keys = [
            "openness",
            "conscientiousness",
            "extraversion",
            "agreeableness",
            "neuroticism",
            "honesty_humility",
            "loss_aversion",
            "risk_aversion_gains",
            "risk_aversion_losses",
            "probability_weighting",
        ]
        return cls(**dict(zip(keys, values, strict=True)))


class EmotionState(BaseModel):
    """Real-time emotion state (VAD + extensions).

    Stored in Redis for fast access, periodically snapshotted to PG.
    """

    # VAD core
    valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal: float = Field(default=0.5, ge=0.0, le=1.0)
    dominance: float = Field(default=0.5, ge=0.0, le=1.0)

    # Extensions
    stress: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
