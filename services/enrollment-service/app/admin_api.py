from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .asset_client import validate_asset_tenant
from .auth import IdentityPrincipal, current_principal, enforce_enrollment_admin
from .database import get_db
from .errors import GuardianError
from .models import EnrollmentToken, OutboxEvent
from .schemas import CreateEnrollmentTokenRequest, EnrollmentTokenCreated, EnrollmentTokenRead
from .tokens import generate_enrollment_token

router = APIRouter(prefix="/api/v1")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _tenant_resolver(request: Request):
    override = getattr(request.app.state, "tenant_access_resolver", None)
    if override is not None:
        return override
    return request.app.state.tenant_access_client.resolve


def _require_admin(request: Request, principal: IdentityPrincipal, tenant_id: str) -> None:
    enforce_enrollment_admin(principal, tenant_id, _tenant_resolver(request))


def _token_status(token: EnrollmentToken) -> str:
    if token.revoked_at is not None:
        return "revoked"
    if token.consumed_at is not None:
        return "consumed"
    if token.reserved_at is not None:
        return "reserved"
    if _utc(token.expires_at) <= datetime.now(UTC):
        return "expired"
    return "active"


def _read(token: EnrollmentToken) -> EnrollmentTokenRead:
    return EnrollmentTokenRead(
        id=token.id,
        tenant_id=token.tenant_id,
        asset_id=token.asset_id,
        token_hint=token.token_hint,
        status=_token_status(token),
        created_at=token.created_at,
        expires_at=token.expires_at,
        revoked_at=token.revoked_at,
        reserved_at=token.reserved_at,
        consumed_at=token.consumed_at,
        consumed_device_id=token.consumed_device_id,
    )


def _token_or_404(session: Session, token_id: str) -> EnrollmentToken:
    token = session.get(EnrollmentToken, token_id)
    if token is None:
        raise GuardianError(404, "enrollment.token_not_found", "Enrollment token not found")
    return token


@router.post(
    "/enrollment-tokens",
    response_model=EnrollmentTokenCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_enrollment_token(
    payload: CreateEnrollmentTokenRequest,
    request: Request,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> EnrollmentTokenCreated:
    _require_admin(request, principal, payload.tenant_id)
    asset = request.app.state.asset_client.get(payload.asset_id, principal.bearer_token)
    validate_asset_tenant(asset, payload.tenant_id)

    plain = generate_enrollment_token()
    now = datetime.now(UTC)
    token = EnrollmentToken(
        token_hash=plain.token_hash,
        token_hint=plain.hint,
        tenant_id=payload.tenant_id,
        asset_id=payload.asset_id,
        created_by_user_id=principal.user_id,
        expires_at=now + timedelta(minutes=payload.expires_in_minutes),
    )
    session.add(token)
    session.flush()
    session.add(
        OutboxEvent(
            event_type="enrollment.token.created",
            aggregate_type="enrollment_token",
            aggregate_id=token.id,
            payload={
                "token_id": token.id,
                "tenant_id": token.tenant_id,
                "asset_id": token.asset_id,
                "token_hint": token.token_hint,
                "expires_at": token.expires_at.isoformat(),
                "created_by_user_id": principal.user_id,
            },
        )
    )
    session.commit()
    session.refresh(token)
    read = _read(token)
    return EnrollmentTokenCreated(**read.model_dump(), token=plain.plaintext)


@router.get("/enrollment-tokens", response_model=list[EnrollmentTokenRead])
def list_enrollment_tokens(
    tenant_id: str,
    request: Request,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> list[EnrollmentTokenRead]:
    _require_admin(request, principal, tenant_id)
    tokens = session.scalars(
        select(EnrollmentToken)
        .where(EnrollmentToken.tenant_id == tenant_id)
        .order_by(EnrollmentToken.created_at, EnrollmentToken.id)
    ).all()
    return [_read(token) for token in tokens]


@router.post("/enrollment-tokens/{token_id}/revoke", response_model=EnrollmentTokenRead)
def revoke_enrollment_token(
    token_id: str,
    request: Request,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
) -> EnrollmentTokenRead:
    token = _token_or_404(session, token_id)
    _require_admin(request, principal, token.tenant_id)
    if token.revoked_at is not None:
        return _read(token)

    token.revoked_at = datetime.now(UTC)
    session.add(
        OutboxEvent(
            event_type="enrollment.token.revoked",
            aggregate_type="enrollment_token",
            aggregate_id=token.id,
            payload={
                "token_id": token.id,
                "tenant_id": token.tenant_id,
                "asset_id": token.asset_id,
                "revoked_at": token.revoked_at.isoformat(),
                "revoked_by_user_id": principal.user_id,
            },
        )
    )
    session.commit()
    session.refresh(token)
    return _read(token)
