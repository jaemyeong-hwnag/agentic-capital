"""Tests for personality models, drift, and emotion."""

import pytest

from agentic_capital.core.personality.drift import apply_drift
from agentic_capital.core.personality.emotion import update_emotion_from_pnl
from agentic_capital.core.personality.models import EmotionState, PersonalityVector


class TestPersonalityVector:
    def test_default_values(self) -> None:
        p = PersonalityVector()
        assert p.openness == 0.5
        assert p.loss_aversion == 0.5

    def test_to_list(self) -> None:
        p = PersonalityVector()
        values = p.to_list()
        assert len(values) == 10
        assert all(v == 0.5 for v in values)

    def test_from_list(self) -> None:
        values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        p = PersonalityVector.from_list(values)
        assert p.openness == 0.1
        assert p.probability_weighting == 1.0

    def test_from_list_roundtrip(self) -> None:
        original = PersonalityVector(openness=0.3, neuroticism=0.8)
        restored = PersonalityVector.from_list(original.to_list())
        assert original == restored

    def test_boundary_values(self) -> None:
        p = PersonalityVector(openness=0.0, neuroticism=1.0)
        assert p.openness == 0.0
        assert p.neuroticism == 1.0

    def test_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError):
            PersonalityVector(openness=1.5)
        with pytest.raises(ValueError):
            PersonalityVector(openness=-0.1)


class TestPersonalityDrift:
    def test_positive_drift(self) -> None:
        p = PersonalityVector(openness=0.5)
        updated, event = apply_drift(p, "openness", 0.1, "big_win", "Successful trade")
        assert updated.openness == pytest.approx(0.6)
        assert event.old_value == 0.5
        assert event.new_value == pytest.approx(0.6)

    def test_negative_drift(self) -> None:
        p = PersonalityVector(neuroticism=0.5)
        updated, _event = apply_drift(p, "neuroticism", -0.2, "promotion", "Gained confidence")
        assert updated.neuroticism == pytest.approx(0.3)

    def test_drift_clamped_at_max(self) -> None:
        p = PersonalityVector(openness=0.9)
        updated, _ = apply_drift(p, "openness", 0.5, "test", "test")
        assert updated.openness == 1.0

    def test_drift_clamped_at_min(self) -> None:
        p = PersonalityVector(openness=0.1)
        updated, _ = apply_drift(p, "openness", -0.5, "test", "test")
        assert updated.openness == 0.0

    def test_drift_event_records_trigger(self) -> None:
        p = PersonalityVector()
        _, event = apply_drift(p, "loss_aversion", 0.05, "big_loss", "Lost 10% on AAPL")
        assert event.trigger_event == "big_loss"
        assert event.reasoning == "Lost 10% on AAPL"


class TestEmotionState:
    def test_default_values(self) -> None:
        e = EmotionState()
        assert e.valence == 0.0
        assert e.arousal == 0.5
        assert e.confidence == 0.5

    def test_pnl_positive_increases_valence(self) -> None:
        e = EmotionState()
        updated = update_emotion_from_pnl(e, 0.05)  # +5%
        assert updated.valence > e.valence

    def test_pnl_negative_decreases_valence(self) -> None:
        e = EmotionState()
        updated = update_emotion_from_pnl(e, -0.05)  # -5%
        assert updated.valence < e.valence

    def test_pnl_negative_increases_stress(self) -> None:
        e = EmotionState()
        updated = update_emotion_from_pnl(e, -0.10)  # -10%
        assert updated.stress > e.stress

    def test_emotion_clamped(self) -> None:
        e = EmotionState(valence=0.9)
        updated = update_emotion_from_pnl(e, 0.5)  # +50%
        assert updated.valence <= 1.0
        assert updated.arousal <= 1.0
