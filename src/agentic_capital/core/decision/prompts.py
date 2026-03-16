"""Compact LLM prompt builders — AI-to-AI optimized format.

All formats use: compact XML tags, abbreviated keys, TOON tables.
~60-75% token reduction vs verbose English-label format.
"""
from agentic_capital.core.personality.models import EmotionState, PersonalityVector
from agentic_capital.formats.compact import LEGEND, MANDATE, psych
from agentic_capital.formats.toon import to_toon


def build_system_prompt(
    name: str,
    role: str,
    philosophy: str,
    personality: PersonalityVector,
    emotion: EmotionState,
) -> str:
    """Compact system prompt with personality injection."""
    return (
        f"{LEGEND}\n"
        f"<agent name=\"{name}\" role=\"{role}\">\n"
        f"<phi>{philosophy or 'maximize returns'}</phi>\n"
        f"{psych(personality, emotion)}\n"
        f"</agent>\n"
        f"{MANDATE}"
    )


def build_trading_prompt(
    balance: float,
    positions: list[dict],
    market_data: list[dict],
    recent_memories: list[str],
) -> str:
    """Compact trading decision prompt."""
    parts = [f"avl:{balance:.0f}"]

    if positions:
        rows = [
            [
                p["symbol"],
                f"{p['quantity']:.0f}",
                f"{p['avg_price']:.0f}",
                f"{p['current_price']:.0f}",
                f"{p['unrealized_pnl_pct']:.2f}",
            ]
            for p in positions
        ]
        parts.append(to_toon("pos", ["sym", "qty", "avg", "cur", "pct"], rows))

    if market_data:
        rows = [
            [
                d["symbol"],
                f"{d['price']:,.0f}",
                f"{d.get('change_pct', 0):.2f}",
                f"{d.get('volume', 0):,.0f}",
            ]
            for d in market_data
        ]
        parts.append(to_toon("mkt", ["sym", "px", "Δ%", "vol"], rows))

    if recent_memories:
        parts.append("mem:" + "|".join(recent_memories[:5]))

    parts.append("JSON:{decisions:[{action:BUY|SELL|HOLD,sym,qty,why}],outlook,cf}")

    return "\n".join(parts)


def build_ceo_prompt(
    agents: list[dict],
    company_state: dict,
    recent_performance: list[dict],
) -> str:
    """Compact CEO organizational decision prompt."""
    cap = company_state.get("total_capital", 0)
    n_ag = company_state.get("total_agents", 0)
    pnl = company_state.get("daily_pnl_pct", 0)
    parts = [f"cap:{cap:.0f}|agents:{n_ag}|pnl:{pnl:.2f}%"]

    if agents:
        rows = [
            [a["name"], a.get("role", ""), f"{a.get('capital', 0):.0f}", f"{a.get('pnl_pct', 0):.2f}"]
            for a in agents
        ]
        parts.append(to_toon("ag", ["name", "role", "cap", "pnl%"], rows))

    parts.append(
        "JSON:{actions:[{type:hire|fire|promote|demote|reallocate|strategy|create_role|abolish_role|noop,"
        "target,detail,reason,capital?}],strategy,cf}"
    )

    return "\n".join(parts)
