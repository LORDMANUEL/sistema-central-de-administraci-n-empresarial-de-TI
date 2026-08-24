from dataclasses import dataclass

import pytest

from app.errors import GuardianError
from app.tenant_access import TenantAccessDecision, enforce_asset_access


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str


def test_platform_admin_is_allowed_without_tenant_lookup():
    principal = Principal(user_id="platform-user", role="platform_admin")
    called = False

    def resolver(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("platform_admin must not need tenant membership lookup")

    decision = enforce_asset_access(principal, "tenant-1", resolver, write=True)

    assert decision.allowed is True
    assert decision.role == "platform_admin"
    assert called is False


def test_org_admin_can_write_assets_for_active_tenant():
    principal = Principal(user_id="org-user", role="user")

    def resolver(tenant_id: str, user_id: str) -> TenantAccessDecision:
        assert tenant_id == "tenant-1"
        assert user_id == "org-user"
        return TenantAccessDecision(allowed=True, role="org_admin", tenant_status="active")

    decision = enforce_asset_access(principal, "tenant-1", resolver, write=True)
    assert decision.allowed is True


def test_regular_member_is_read_only():
    principal = Principal(user_id="member-user", role="user")

    def resolver(*args) -> TenantAccessDecision:
        return TenantAccessDecision(allowed=True, role="member", tenant_status="active")

    assert enforce_asset_access(principal, "tenant-1", resolver, write=False).allowed is True
    with pytest.raises(GuardianError) as exc:
        enforce_asset_access(principal, "tenant-1", resolver, write=True)
    assert exc.value.status_code == 403
    assert exc.value.code == "asset.org_admin_required"


def test_suspended_tenant_is_denied():
    principal = Principal(user_id="org-user", role="user")

    def resolver(*args) -> TenantAccessDecision:
        return TenantAccessDecision(allowed=True, role="org_admin", tenant_status="suspended")

    with pytest.raises(GuardianError) as exc:
        enforce_asset_access(principal, "tenant-1", resolver, write=False)
    assert exc.value.code == "asset.tenant_suspended"


def test_missing_or_inactive_membership_is_denied():
    principal = Principal(user_id="outsider", role="user")

    def resolver(*args) -> TenantAccessDecision:
        return TenantAccessDecision(allowed=False, role=None, tenant_status="active")

    with pytest.raises(GuardianError) as exc:
        enforce_asset_access(principal, "tenant-1", resolver, write=False)
    assert exc.value.code == "asset.access_denied"
