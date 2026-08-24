from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import IdentityPrincipal, current_principal
from .database import get_db
from .errors import GuardianError
from .models import Asset, ExternalIdentity, OutboxEvent
from .schemas import AssetCreate, AssetRead, ExternalIdentityCreate, ExternalIdentityRead
from .tenant_access import TenantAccessDecision, enforce_asset_access

router = APIRouter(prefix="/api/v1")


def _outbox(event_type: str, aggregate_id: str, payload: dict) -> OutboxEvent:
    return OutboxEvent(
        event_type=event_type,
        aggregate_type="asset",
        aggregate_id=aggregate_id,
        payload=payload,
    )


def _asset_or_404(session: Session, asset_id: str) -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise GuardianError(404, "asset.not_found", "Asset not found")
    return asset


def _resolver(request: Request, principal: IdentityPrincipal) -> Callable[[str, str], TenantAccessDecision]:
    override = getattr(request.app.state, "tenant_access_resolver", None)
    if override is not None:
        return override
    return lambda tenant_id, user_id: request.app.state.tenant_access_client.resolve(
        tenant_id,
        user_id,
        principal.bearer_token,
    )


def _enforce(
    request: Request,
    principal: IdentityPrincipal,
    tenant_id: str,
    *,
    write: bool,
) -> TenantAccessDecision:
    return enforce_asset_access(
        principal,
        tenant_id,
        _resolver(request, principal),
        write=write,
    )


def _validate_references(
    request: Request,
    principal: IdentityPrincipal,
    tenant_id: str,
    site_id: str | None,
    department_id: str | None,
) -> None:
    override = getattr(request.app.state, "tenant_reference_validator", None)
    if override is not None:
        override(tenant_id, site_id, department_id)
        return
    if getattr(request.app.state, "auth_disabled", False):
        return
    request.app.state.tenant_access_client.validate_references(
        tenant_id,
        principal.bearer_token,
        site_id=site_id,
        department_id=department_id,
    )


@router.post("/assets", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreate,
    request: Request,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> Asset:
    _enforce(request, principal, payload.tenant_id, write=True)
    _validate_references(
        request,
        principal,
        payload.tenant_id,
        payload.site_id,
        payload.department_id,
    )
    asset = Asset(**payload.model_dump())
    session.add(asset)
    session.flush()
    session.add(
        _outbox(
            "asset.created",
            asset.guardian_asset_id,
            {
                "guardian_asset_id": asset.guardian_asset_id,
                "tenant_id": asset.tenant_id,
                "site_id": asset.site_id,
                "department_id": asset.department_id,
                "asset_type": asset.asset_type,
                "display_name": asset.display_name,
                "actor_user_id": principal.user_id,
            },
        )
    )
    session.commit()
    session.refresh(asset)
    return asset


@router.get("/assets", response_model=list[AssetRead])
def list_assets(
    tenant_id: str,
    request: Request,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> list[Asset]:
    _enforce(request, principal, tenant_id, write=False)
    return list(
        session.scalars(
            select(Asset).where(Asset.tenant_id == tenant_id).order_by(Asset.display_name, Asset.guardian_asset_id)
        ).all()
    )


@router.get("/assets/{asset_id}", response_model=AssetRead)
def get_asset(
    asset_id: str,
    request: Request,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> Asset:
    asset = _asset_or_404(session, asset_id)
    _enforce(request, principal, asset.tenant_id, write=False)
    return asset


@router.post(
    "/assets/{asset_id}/external-identities",
    response_model=ExternalIdentityRead,
    status_code=status.HTTP_201_CREATED,
)
def link_external_identity(
    asset_id: str,
    payload: ExternalIdentityCreate,
    response: Response,
    request: Request,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> ExternalIdentity:
    asset = _asset_or_404(session, asset_id)
    _enforce(request, principal, asset.tenant_id, write=True)
    existing = session.scalar(
        select(ExternalIdentity).where(
            ExternalIdentity.provider == payload.provider,
            ExternalIdentity.external_id == payload.external_id,
        )
    )
    if existing is not None:
        if existing.guardian_asset_id != asset.guardian_asset_id:
            raise GuardianError(
                409,
                "asset.external_identity_conflict",
                "External identity is already linked to another asset",
            )
        response.status_code = status.HTTP_200_OK
        return existing

    identity = ExternalIdentity(
        guardian_asset_id=asset.guardian_asset_id,
        provider=payload.provider,
        external_id=payload.external_id,
    )
    session.add(identity)
    try:
        session.flush()
        session.add(
            _outbox(
                "asset.external_identity.linked",
                asset.guardian_asset_id,
                {
                    "guardian_asset_id": asset.guardian_asset_id,
                    "tenant_id": asset.tenant_id,
                    "provider": identity.provider,
                    "external_id": identity.external_id,
                    "actor_user_id": principal.user_id,
                },
            )
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise GuardianError(
            409,
            "asset.external_identity_conflict",
            "External identity is already linked to another asset",
        ) from exc
    session.refresh(identity)
    return identity