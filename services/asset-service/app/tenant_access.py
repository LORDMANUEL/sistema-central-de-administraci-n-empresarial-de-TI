from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from .errors import GuardianError


class PrincipalLike(Protocol):
    user_id: str
    role: str


@dataclass(frozen=True)
class TenantAccessDecision:
    allowed: bool
    role: str | None
    tenant_status: str


TenantAccessResolver = Callable[[str, str], TenantAccessDecision]


def enforce_asset_access(
    principal: PrincipalLike,
    tenant_id: str,
    resolver: TenantAccessResolver,
    *,
    write: bool,
) -> TenantAccessDecision:
    if principal.role == "platform_admin":
        return TenantAccessDecision(allowed=True, role="platform_admin", tenant_status="active")

    decision = resolver(tenant_id, principal.user_id)
    if decision.tenant_status != "active":
        raise GuardianError(403, "asset.tenant_suspended", "Tenant is suspended")
    if not decision.allowed:
        raise GuardianError(403, "asset.access_denied", "You do not have access to this tenant")
    if write and decision.role != "org_admin":
        raise GuardianError(403, "asset.org_admin_required", "Tenant organization administrator role is required")
    return decision
