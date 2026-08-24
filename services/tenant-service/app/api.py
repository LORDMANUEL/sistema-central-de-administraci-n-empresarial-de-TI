from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import IdentityPrincipal, current_principal, require_platform_admin
from .database import get_db
from .errors import GuardianError
from .models import (
    Department,
    MembershipRole,
    OutboxEvent,
    Site,
    Tenant,
    TenantMembership,
    TenantStatus,
)
from .schemas import (
    DepartmentCreate,
    DepartmentResponse,
    DepartmentUpdate,
    MembershipResponse,
    MembershipUpdate,
    MembershipUpsert,
    SiteCreate,
    SiteResponse,
    SiteUpdate,
    TenantCreate,
    TenantResponse,
    TenantUpdate,
)

router = APIRouter(prefix="/api/v1")


def _outbox(event_type: str, aggregate_type: str, aggregate_id: str, payload: dict) -> OutboxEvent:
    return OutboxEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
    )


def _tenant_or_404(session: Session, tenant_id: str) -> Tenant:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise GuardianError(404, "tenant.not_found", "Tenant not found")
    return tenant


def _membership(session: Session, tenant_id: str, user_id: str) -> TenantMembership | None:
    return session.scalar(
        select(TenantMembership).where(
            TenantMembership.tenant_id == tenant_id,
            TenantMembership.user_id == user_id,
        )
    )


def _tenant_access(
    session: Session,
    tenant_id: str,
    principal: IdentityPrincipal,
    *,
    require_org_admin: bool = False,
) -> tuple[Tenant, TenantMembership | None]:
    tenant = _tenant_or_404(session, tenant_id)
    if principal.role == "platform_admin":
        return tenant, None
    membership = _membership(session, tenant_id, principal.user_id)
    if membership is None or not membership.is_active:
        raise GuardianError(403, "tenant.access_denied", "You do not have access to this tenant")
    if tenant.status == TenantStatus.SUSPENDED:
        raise GuardianError(403, "tenant.suspended", "Tenant is suspended")
    if require_org_admin and membership.role != MembershipRole.ORG_ADMIN:
        raise GuardianError(403, "tenant.org_admin_required", "Tenant organization administrator role is required")
    return tenant, membership


@router.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    payload: TenantCreate,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(require_platform_admin),
) -> Tenant:
    tenant = Tenant(**payload.model_dump())
    session.add(tenant)
    try:
        session.flush()
        session.add(
            _outbox(
                "tenant.created",
                "tenant",
                tenant.id,
                {"tenant_id": tenant.id, "slug": tenant.slug, "actor_user_id": principal.user_id},
            )
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise GuardianError(409, "tenant.slug_already_exists", "Tenant slug already exists") from exc
    session.refresh(tenant)
    return tenant


@router.get("/tenants", response_model=list[TenantResponse])
def list_tenants(
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> list[Tenant]:
    if principal.role == "platform_admin":
        statement = select(Tenant).order_by(Tenant.name)
    else:
        statement = (
            select(Tenant)
            .join(TenantMembership, TenantMembership.tenant_id == Tenant.id)
            .where(
                TenantMembership.user_id == principal.user_id,
                TenantMembership.is_active.is_(True),
                Tenant.status == TenantStatus.ACTIVE,
            )
            .order_by(Tenant.name)
        )
    return list(session.scalars(statement).all())


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
def get_tenant(
    tenant_id: str,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> Tenant:
    tenant, _ = _tenant_access(session, tenant_id, principal)
    return tenant


@router.patch("/tenants/{tenant_id}", response_model=TenantResponse)
def update_tenant(
    tenant_id: str,
    payload: TenantUpdate,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> Tenant:
    tenant, _ = _tenant_access(session, tenant_id, principal, require_org_admin=True)
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(tenant, key, value)
    session.add(
        _outbox(
            "tenant.updated",
            "tenant",
            tenant.id,
            {"tenant_id": tenant.id, "changes": {k: str(v) for k, v in changes.items()}, "actor_user_id": principal.user_id},
        )
    )
    session.commit()
    session.refresh(tenant)
    return tenant


@router.post("/tenants/{tenant_id}/memberships", response_model=MembershipResponse, status_code=status.HTTP_201_CREATED)
def upsert_membership(
    tenant_id: str,
    payload: MembershipUpsert,
    response: Response,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> TenantMembership:
    tenant, _ = _tenant_access(session, tenant_id, principal, require_org_admin=True)
    user_id = str(payload.user_id)
    membership = _membership(session, tenant_id, user_id)
    created = membership is None
    if membership is None:
        membership = TenantMembership(tenant_id=tenant.id, user_id=user_id, role=payload.role, is_active=True)
        session.add(membership)
        session.flush()
    else:
        membership.role = payload.role
        membership.is_active = True
    session.add(
        _outbox(
            "tenant.membership.upserted",
            "tenant_membership",
            membership.id,
            {
                "tenant_id": tenant.id,
                "membership_id": membership.id,
                "user_id": membership.user_id,
                "role": membership.role.value,
                "is_active": membership.is_active,
                "actor_user_id": principal.user_id,
            },
        )
    )
    session.commit()
    session.refresh(membership)
    if not created:
        response.status_code = status.HTTP_200_OK
    return membership


@router.get("/tenants/{tenant_id}/memberships", response_model=list[MembershipResponse])
def list_memberships(
    tenant_id: str,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> list[TenantMembership]:
    _tenant_access(session, tenant_id, principal, require_org_admin=True)
    return list(
        session.scalars(
            select(TenantMembership)
            .where(TenantMembership.tenant_id == tenant_id)
            .order_by(TenantMembership.user_id)
        ).all()
    )


@router.patch("/tenants/{tenant_id}/memberships/{user_id}", response_model=MembershipResponse)
def update_membership(
    tenant_id: str,
    user_id: str,
    payload: MembershipUpdate,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> TenantMembership:
    tenant, _ = _tenant_access(session, tenant_id, principal, require_org_admin=True)
    membership = _membership(session, tenant_id, user_id)
    if membership is None:
        raise GuardianError(404, "tenant.membership_not_found", "Tenant membership not found")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(membership, key, value)
    session.add(
        _outbox(
            "tenant.membership.upserted",
            "tenant_membership",
            membership.id,
            {
                "tenant_id": tenant.id,
                "membership_id": membership.id,
                "user_id": membership.user_id,
                "role": membership.role.value,
                "is_active": membership.is_active,
                "actor_user_id": principal.user_id,
            },
        )
    )
    session.commit()
    session.refresh(membership)
    return membership


def _site_or_404(session: Session, tenant_id: str, site_id: str) -> Site:
    site = session.get(Site, site_id)
    if site is None or site.tenant_id != tenant_id:
        raise GuardianError(404, "tenant.site_not_found", "Site not found")
    return site


@router.post("/tenants/{tenant_id}/sites", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
def create_site(
    tenant_id: str,
    payload: SiteCreate,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> Site:
    tenant, _ = _tenant_access(session, tenant_id, principal, require_org_admin=True)
    site = Site(tenant_id=tenant.id, **payload.model_dump())
    session.add(site)
    try:
        session.flush()
        session.add(
            _outbox(
                "tenant.site.created",
                "site",
                site.id,
                {"tenant_id": tenant.id, "site_id": site.id, "code": site.code, "actor_user_id": principal.user_id},
            )
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise GuardianError(409, "tenant.site_code_already_exists", "Site code already exists in tenant") from exc
    session.refresh(site)
    return site


@router.get("/tenants/{tenant_id}/sites", response_model=list[SiteResponse])
def list_sites(
    tenant_id: str,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> list[Site]:
    _tenant_access(session, tenant_id, principal)
    return list(session.scalars(select(Site).where(Site.tenant_id == tenant_id).order_by(Site.code)).all())


@router.patch("/tenants/{tenant_id}/sites/{site_id}", response_model=SiteResponse)
def update_site(
    tenant_id: str,
    site_id: str,
    payload: SiteUpdate,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> Site:
    tenant, _ = _tenant_access(session, tenant_id, principal, require_org_admin=True)
    site = _site_or_404(session, tenant.id, site_id)
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(site, key, value)
    session.add(
        _outbox(
            "tenant.site.updated",
            "site",
            site.id,
            {"tenant_id": tenant.id, "site_id": site.id, "changes": {k: str(v) for k, v in changes.items()}, "actor_user_id": principal.user_id},
        )
    )
    session.commit()
    session.refresh(site)
    return site


def _department_or_404(session: Session, tenant_id: str, department_id: str) -> Department:
    department = session.get(Department, department_id)
    if department is None or department.tenant_id != tenant_id:
        raise GuardianError(404, "tenant.department_not_found", "Department not found")
    return department


def _validate_department_parent(
    session: Session,
    tenant_id: str,
    parent_id: str | None,
    *,
    department_id: str | None = None,
) -> Department | None:
    if parent_id is None:
        return None
    parent = session.get(Department, parent_id)
    if parent is None or parent.tenant_id != tenant_id:
        raise GuardianError(409, "tenant.department_parent_invalid", "Parent department must belong to the same tenant")
    visited: set[str] = set()
    current: Department | None = parent
    while current is not None:
        if current.id in visited:
            raise GuardianError(409, "tenant.department_cycle", "Department hierarchy contains a cycle")
        visited.add(current.id)
        if department_id is not None and current.id == department_id:
            raise GuardianError(409, "tenant.department_cycle", "Department hierarchy cannot contain a cycle")
        if current.parent_id is None:
            break
        next_department = session.get(Department, current.parent_id)
        if next_department is None or next_department.tenant_id != tenant_id:
            raise GuardianError(409, "tenant.department_parent_invalid", "Parent department must belong to the same tenant")
        current = next_department
    return parent


@router.post(
    "/tenants/{tenant_id}/departments",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_department(
    tenant_id: str,
    payload: DepartmentCreate,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> Department:
    tenant, _ = _tenant_access(session, tenant_id, principal, require_org_admin=True)
    parent_id = str(payload.parent_id) if payload.parent_id is not None else None
    _validate_department_parent(session, tenant.id, parent_id)
    department = Department(
        tenant_id=tenant.id,
        code=payload.code,
        name=payload.name,
        parent_id=parent_id,
    )
    session.add(department)
    try:
        session.flush()
        session.add(
            _outbox(
                "tenant.department.created",
                "department",
                department.id,
                {
                    "tenant_id": tenant.id,
                    "department_id": department.id,
                    "code": department.code,
                    "parent_id": department.parent_id,
                    "actor_user_id": principal.user_id,
                },
            )
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise GuardianError(
            409,
            "tenant.department_code_already_exists",
            "Department code already exists in tenant",
        ) from exc
    session.refresh(department)
    return department


@router.get("/tenants/{tenant_id}/departments", response_model=list[DepartmentResponse])
def list_departments(
    tenant_id: str,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> list[Department]:
    _tenant_access(session, tenant_id, principal)
    return list(
        session.scalars(
            select(Department).where(Department.tenant_id == tenant_id).order_by(Department.code)
        ).all()
    )


@router.patch(
    "/tenants/{tenant_id}/departments/{department_id}",
    response_model=DepartmentResponse,
)
def update_department(
    tenant_id: str,
    department_id: str,
    payload: DepartmentUpdate,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> Department:
    tenant, _ = _tenant_access(session, tenant_id, principal, require_org_admin=True)
    department = _department_or_404(session, tenant.id, department_id)
    changes = payload.model_dump(exclude_unset=True)
    if "parent_id" in changes:
        parent_id = str(changes["parent_id"]) if changes["parent_id"] is not None else None
        _validate_department_parent(session, tenant.id, parent_id, department_id=department.id)
        changes["parent_id"] = parent_id
    for key, value in changes.items():
        setattr(department, key, value)
    session.add(
        _outbox(
            "tenant.department.updated",
            "department",
            department.id,
            {
                "tenant_id": tenant.id,
                "department_id": department.id,
                "changes": {k: str(v) for k, v in changes.items()},
                "actor_user_id": principal.user_id,
            },
        )
    )
    session.commit()
    session.refresh(department)
    return department
