"""Organization audit helpers for autonomous agent rosters."""

from __future__ import annotations

from typing import Any


def audit_roster(agents: list[Any]) -> dict[str, Any]:
    """Return compact health evidence for the current autonomous roster.

    The audit is observational only. It never blocks CEO/agent HR decisions;
    it exposes whether the runtime can safely execute and record those
    decisions.
    """
    names: list[str] = []
    ids: list[str] = []
    issues: list[str] = []
    roster: list[dict[str, str]] = []

    for agent in agents:
        name = str(getattr(agent, "name", ""))
        agent_id = str(getattr(agent, "agent_id", ""))
        role = str(getattr(agent, "role", "") or getattr(getattr(agent, "profile", None), "role", "") or "")
        runtime_class = type(agent).__name__
        names.append(name)
        ids.append(agent_id)
        roster.append(
            {
                "id": agent_id,
                "name": name,
                "role": role or runtime_class,
                "runtime_class": runtime_class,
            }
        )

        if runtime_class == "TraderAgent" and getattr(agent, "_trading", None) is None:
            issues.append(f"trader_without_trading_adapter:{name}")
        if not role:
            issues.append(f"missing_declared_role:{name}")

    duplicate_names = sorted({name for name in names if names.count(name) > 1 and name})
    duplicate_ids = sorted({agent_id for agent_id in ids if ids.count(agent_id) > 1 and agent_id})
    if duplicate_names:
        issues.append(f"duplicate_agent_names:{','.join(duplicate_names)}")
    if duplicate_ids:
        issues.append(f"duplicate_agent_ids:{','.join(duplicate_ids)}")
    if not agents:
        issues.append("empty_roster")

    return {
        "ok": not issues,
        "agents_count": len(agents),
        "active_agents": roster,
        "issues": issues,
        "constraints": [
            "observational_only",
            "does_not_block_hr_autonomy",
            "capital_limits_enforced_elsewhere",
            "no_direct_agent_to_agent_runtime_mutation",
        ],
    }
