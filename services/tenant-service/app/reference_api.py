from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import IdentityPrincipal, current_principal
from .database import get_db
from .errors import GuardianError
from .models import Department, DepartmentStatus, Site, SiteStatus, Tenant, TenantMembership

router = APIRouter(prefix="/api/v1")


class ReferenceRequest(BaseModel):
    site_id: UUID | None = None
    department_id: UUID | None = None


class ReferenceResponse(BaseModel):
    valid: bool
    tenant_id: str
    site_id: str | None
    department_id: str | None


def _require_access(session: Session, tenant: Tenant, principal: IdentityPrincipal) -> None:
    if principal.role == "platform_admin":
        return
    membership = session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.user_id == principal.user_id,
            TenantMembership.is_active.is_(True),
        )
    )
    if membership is None:
        raise GuardianError(403, "tenant.access_denied", "You do not have access to this tenant")
    if tenant.status.value != "active":
        raise GuardianError(403, "tenant.suspended", "Tenant is suspended")


@router.post("/tenants/{tenant_id}/references/validate", response_model=ReferenceResponse)
def validate_references(
    tenant_id: str,
    payload: ReferenceRequest,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> ReferenceResponse:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise GuardianError(404, "tenant.not_found", "Tenant not found")
    _require_access(session, tenant, principal)
    site_id = str(payload.site_id) if payload.site_id is not None else None
    department_id = str(payload.department_id) if payload.department_id is not None else None

    if site_id is not None:
        site = session.get(Site, site_id)
        if site is None or site.tenant_id != tenant_id or site.status != SiteStatus.ACTIVE:
            raise GuardianError(422, "tenant.site_reference_invalid", "Site reference must belong to the active tenant")
    if department_id is not None:
        department = session.get(Department, department_id)
        if department is None or department.tenant_id != tenant_id or department.status != DepartmentStatus.ACTIVE:
            raise GuardianError(422, "tenant.department_reference_invalid", "Department reference must belong to the active tenant")

    return ReferenceResponse(valid=True, tenant_id=tenant_id, site_id=site_id, department_id=department_id)
