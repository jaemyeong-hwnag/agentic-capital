"""Unit tests for compact prompt templates."""

import pytest

from agentic_capital.core.decision.prompts import (
    build_ceo_prompt,
    build_system_prompt,
    build_trading_prompt,
)
from agentic_capital.core.personality.models import EmotionState, PersonalityVector


class TestSystemPrompt:
    def test_includes_personality(self):
        p = PersonalityVector()
        e = EmotionState()
        prompt = build_system_prompt("Alpha", "trader", "aggressive", p, e)
        assert "Alpha" in prompt
        assert "trader" in prompt
        assert "aggressive" in prompt
        assert "O:" in prompt       # compact Big5 abbreviation
        assert "LA:" in prompt      # compact loss_aversion

    def test_includes_emotion(self):
        p = PersonalityVector()
        e = EmotionState(valence=0.8, stress=0.2)
        prompt = build_system_prompt("Beta", "analyst", "", p, e)
        assert "V:0.80" in prompt   # compact valence
        assert "ST:0.20" in prompt  # compact stress

    def test_default_philosophy(self):
        prompt = build_system_prompt("X", "trader", "", PersonalityVector(), EmotionState())
        assert "maximize returns" in prompt

    def test_json_instruction(self):
        prompt = build_system_prompt("X", "trader", "", PersonalityVector(), EmotionState())
        assert "GOAL=profit" in prompt


class TestTradingPrompt:
    def test_includes_balance(self):
        prompt = build_trading_prompt(1_000_000, [], [], [])
        assert "avl:1000000" in prompt   # compact balance

    def test_includes_positions(self):
        positions = [
            {"symbol": "005930", "quantity": 10, "avg_price": 70000, "current_price": 72000, "unrealized_pnl_pct": 2.86}
        ]
        prompt = build_trading_prompt(500_000, positions, [], [])
        assert "005930" in prompt
        assert "@pos" in prompt          # compact TOON name

    def test_includes_market_data(self):
        mkt = [{"symbol": "005930", "price": 72000, "change_pct": 1.5, "volume": 5000000}]
        prompt = build_trading_prompt(500_000, [], mkt, [])
        assert "@mkt" in prompt          # compact TOON name
        assert "005930" in prompt

    def test_includes_memories(self):
        memories = ["Cycle 1: BUY 005930 x10"]
        prompt = build_trading_prompt(500_000, [], [], memories)
        assert "Cycle 1" in prompt

    def test_decision_instruction(self):
        prompt = build_trading_prompt(500_000, [], [], [])
        assert "BUY" in prompt
        assert "SELL" in prompt
        assert "HOLD" in prompt


class TestCeoPrompt:
    def test_includes_company_state(self):
        prompt = build_ceo_prompt(
            [], {"total_capital": 10_000_000, "total_agents": 3, "daily_pnl_pct": 1.5}, []
        )
        assert "cap:10000000" in prompt  # compact capital
        assert "hire" in prompt

    def test_includes_agents(self):
        agents = [{"name": "Alpha", "role": "trader", "capital": 1_000_000, "pnl_pct": 2.5}]
        prompt = build_ceo_prompt(agents, {"total_capital": 0, "total_agents": 1, "daily_pnl_pct": 0}, [])
        assert "Alpha" in prompt
        assert "@ag" in prompt           # compact TOON name
