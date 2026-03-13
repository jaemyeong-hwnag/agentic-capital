"""Dynamic role system — CEO creates/modifies/abolishes roles freely."""

from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Role(BaseModel):
    """A dynamically defined organizational role.

    Roles are not hardcoded — CEO creates them as needed.
    """

    id: UUID = Field(default_factory=uuid4)
    name: str
    permissions: list[str] = Field(default_factory=list)
    report_to: UUID | None = None  # Parent role
    created_by: UUID | None = None
    status: str = "active"  # active, abolished
