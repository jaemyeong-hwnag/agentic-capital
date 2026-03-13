"""Tests for organization system — roles, permissions, HR."""

from uuid import uuid4

from agentic_capital.core.organization.hr import HREvent, HREventType
from agentic_capital.core.organization.permissions import PermissionGrant, has_permission
from agentic_capital.core.organization.roles import Role


class TestRoles:
    def test_create_role(self) -> None:
        role = Role(name="CIO", permissions=["trade_all", "allocate_capital"])
        assert role.name == "CIO"
        assert role.status == "active"
        assert "trade_all" in role.permissions

    def test_role_hierarchy(self) -> None:
        ceo_role = Role(name="CEO", permissions=["all"])
        cio_role = Role(name="CIO", permissions=["trade_all"], report_to=ceo_role.id)
        assert cio_role.report_to == ceo_role.id


class TestPermissions:
    def test_has_specific_permission(self) -> None:
        assert has_permission(["trade_crypto", "trade_us_stock"], "trade_crypto")
        assert not has_permission(["trade_crypto"], "trade_us_stock")

    def test_all_permission_grants_everything(self) -> None:
        assert has_permission(["all"], "trade_crypto")
        assert has_permission(["all"], "hire_junior")
        assert has_permission(["all"], "anything")

    def test_empty_permissions(self) -> None:
        assert not has_permission([], "trade_crypto")

    def test_permission_grant(self) -> None:
        grant = PermissionGrant(
            agent_id=uuid4(),
            permissions=["trade_crypto", "hire_junior"],
            delegated_by=uuid4(),
            reason="암호화폐팀 리드로 임명",
        )
        assert len(grant.permissions) == 2


class TestHREvents:
    def test_hire_event(self) -> None:
        event = HREvent(
            event_type=HREventType.HIRE,
            target_agent_id=uuid4(),
            decided_by=uuid4(),
            new_role_id=uuid4(),
            new_capital=50_000.0,
            reasoning="Need more analysts for crypto market",
        )
        assert event.event_type == HREventType.HIRE

    def test_fire_event(self) -> None:
        event = HREvent(
            event_type=HREventType.FIRE,
            target_agent_id=uuid4(),
            decided_by=uuid4(),
            old_capital=30_000.0,
            new_capital=0.0,
            reasoning="Consistent underperformance over 30 days",
        )
        assert event.event_type == HREventType.FIRE
