"""Permission system — fluid delegation and revocation."""

from uuid import UUID

from pydantic import BaseModel, Field


class PermissionGrant(BaseModel):
    """Record of a permission grant/revocation."""

    agent_id: UUID
    permissions: list[str] = Field(default_factory=list)
    delegated_by: UUID
    reason: str = ""


def has_permission(agent_permissions: list[str], required: str) -> bool:
    """Check if an agent has a specific permission."""
    return required in agent_permissions or "all" in agent_permissions
