from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import IdentityPrincipal, current_principal
from .database import get_db
from .errors import GuardianError
from .models import Tenant, TenantMembership

router = APIRouter(prefix="/api/v1")


class TenantAccessResponse(BaseModel):
    allowed: bool
    role: str | None
    tenant_status: str


def _tenant_or_404(session: Session, tenant_id: str) -> Tenant:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise GuardianError(404, "tenant.not_found", "Tenant not found")
    return tenant


def _active_membership(session: Session, tenant_id: str, user_id: str) -> TenantMembership | None:
    return session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
            TenantMembership.is_active.is_(True),
        )
    )


@router.get("/tenants/{tenant_id}/access", response_model=TenantAccessResponse)
def resolve_tenant_access(
    tenant_id: str,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> TenantAccessResponse:
    tenant = _tenant_or_404(session, tenant_id)
    if principal.role == "platform_admin":
        return TenantAccessResponse(allowed=True, role="platform_admin", tenant_status=tenant.status.value)
    membership = _active_membership(session, tenant_id, principal.user_id)
    if membership is None:
        raise GuardianError(403, "tenant.access_denied", "You do not have access to this tenant")
    return TenantAccessResponse(allowed=True, role=membership.role.value, tenant_status=tenant.status.value)
