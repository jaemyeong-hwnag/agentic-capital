"""LLM prompt templates — personality injection, TOON/YAML/Markdown-KV format."""

from agentic_capital.core.personality.models import EmotionState, PersonalityVector
from agentic_capital.formats.markdown_kv import to_markdown_kv
from agentic_capital.formats.toon import to_toon


def build_system_prompt(
    name: str,
    role: str,
    philosophy: str,
    personality: PersonalityVector,
    emotion: EmotionState,
) -> str:
    """Build system prompt with personality injection (YAML-style)."""
    p = personality
    return f"""You are {name}, a {role} at an autonomous AI investment fund.

philosophy: {philosophy or 'Maximize returns through rational analysis'}

personality:
  openness: {p.openness:.2f}
  conscientiousness: {p.conscientiousness:.2f}
  extraversion: {p.extraversion:.2f}
  agreeableness: {p.agreeableness:.2f}
  neuroticism: {p.neuroticism:.2f}
  honesty_humility: {p.honesty_humility:.2f}
  loss_aversion: {p.loss_aversion:.2f}
  risk_aversion_gains: {p.risk_aversion_gains:.2f}
  risk_aversion_losses: {p.risk_aversion_losses:.2f}
  probability_weighting: {p.probability_weighting:.2f}

current_emotion:
  valence: {emotion.valence:.2f}
  arousal: {emotion.arousal:.2f}
  dominance: {emotion.dominance:.2f}
  stress: {emotion.stress:.2f}
  confidence: {emotion.confidence:.2f}

Your personality traits deeply influence your investment decisions:
- High loss_aversion means you strongly prefer avoiding losses over gaining profits.
- High neuroticism means market volatility affects you more emotionally.
- High conscientiousness means you prefer thorough analysis before acting.
- Your current stress and confidence levels should affect your risk appetite.

RULES:
- You MUST respond in valid JSON only.
- Your only goal is making money. No other constraints except available capital.
- Be specific about symbols, quantities, and reasoning."""


def build_trading_prompt(
    balance: float,
    positions: list[dict],
    market_data: list[dict],
    recent_memories: list[str],
) -> str:
    """Build trading decision prompt with market context."""
    parts = []

    # Balance (Markdown-KV)
    parts.append("## Account")
    parts.append(to_markdown_kv({"available_cash": f"{balance:,.0f} KRW"}))

    # Positions (TOON)
    if positions:
        pos_rows = [
            [p["symbol"], f"{p['quantity']:.0f}", f"{p['avg_price']:.0f}", f"{p['current_price']:.0f}", f"{p['unrealized_pnl_pct']:.2f}%"]
            for p in positions
        ]
        parts.append("\n## Positions")
        parts.append(to_toon("positions", ["symbol", "qty", "avg_price", "current", "pnl_pct"], pos_rows))

    # Market data (TOON)
    if market_data:
        mkt_rows = [
            [d["symbol"], f"{d['price']:,.0f}", f"{d.get('change_pct', 0):.2f}%", f"{d.get('volume', 0):,.0f}"]
            for d in market_data
        ]
        parts.append("\n## Market")
        parts.append(to_toon("market", ["symbol", "price", "change_pct", "volume"], mkt_rows))

    # Recent memories
    if recent_memories:
        parts.append("\n## Recent Experience")
        for mem in recent_memories[:5]:
            parts.append(f"- {mem}")

    # Instruction
    parts.append("""
## Decision Required

Analyze the market data, your positions, and available capital.
Decide: BUY, SELL, or HOLD for each symbol you're interested in.

Respond in JSON format:
{
  "decisions": [
    {
      "action": "BUY" | "SELL" | "HOLD",
      "symbol": "005930",
      "quantity": 10,
      "reason": "brief reasoning"
    }
  ],
  "market_outlook": "brief overall market assessment",
  "confidence": 0.0 to 1.0
}""")

    return "\n".join(parts)


def build_ceo_prompt(
    agents: list[dict],
    company_state: dict,
    recent_performance: list[dict],
) -> str:
    """Build CEO organizational decision prompt."""
    parts = []

    parts.append("## Company State")
    parts.append(to_markdown_kv({
        "total_capital": f"{company_state.get('total_capital', 0):,.0f} KRW",
        "total_agents": str(company_state.get("total_agents", 0)),
        "daily_pnl_pct": f"{company_state.get('daily_pnl_pct', 0):.2f}%",
    }))

    if agents:
        agent_rows = [
            [a["name"], a.get("role", "trader"), f"{a.get('capital', 0):,.0f}", f"{a.get('pnl_pct', 0):.2f}%"]
            for a in agents
        ]
        parts.append("\n## Agents")
        parts.append(to_toon("agents", ["name", "role", "capital", "pnl_pct"], agent_rows))

    parts.append("""
## CEO Decision Required

As CEO, evaluate the organization and make strategic decisions.
You can: hire new agents, fire underperformers, reallocate capital, change strategy.

Respond in JSON:
{
  "actions": [
    {
      "type": "hire" | "fire" | "reallocate" | "strategy",
      "target": "agent name or new agent description",
      "detail": "specifics",
      "reason": "reasoning"
    }
  ],
  "strategy_update": "brief strategy direction",
  "confidence": 0.0 to 1.0
}""")

    return "\n".join(parts)
