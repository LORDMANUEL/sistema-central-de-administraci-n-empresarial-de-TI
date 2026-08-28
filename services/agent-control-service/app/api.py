from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .admin import device_to_admin_dict, list_visible_devices
from .auth import IdentityPrincipal, current_principal
from .database import get_db
from .device_auth import current_device_principal
from .errors import GuardianError
from .heartbeat import DeviceBindingConflict, DeviceDisabled, apply_heartbeat
from .metrics import HEARTBEATS
from .models import DeviceSession
from .principal import DevicePrincipal
from .schemas import HeartbeatInput

router = APIRouter(prefix="/api/v1")
internal_router = APIRouter(prefix="/internal/v1")


@router.get("/devices")
def list_devices(
    request: Request,
    tenant_id: UUID | None = None,
    state: Literal["online", "offline"] | None = None,
    limit: int = 100,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
):
    if tenant_id is not None:
        request.app.state.tenant_access.require_tenant(tenant_id, principal.bearer_token)
        accessible_tenants = {tenant_id}
    else:
        accessible_tenants = request.app.state.tenant_access.accessible_tenant_ids(principal.bearer_token)
    return [
        device_to_admin_dict(row)
        for row in list_visible_devices(
            session,
            accessible_tenants,
            tenant_id=tenant_id,
            state=state,
            limit=limit,
        )
    ]


@router.get("/devices/{device_id}")
def get_device(
    device_id: UUID,
    request: Request,
    session: Session = Depends(get_db),
    principal: IdentityPrincipal = Depends(current_principal),
):
    device = session.get(DeviceSession, device_id)
    if device is None:
        raise GuardianError(404, "agent_control.device_not_found", "Device not found")
    request.app.state.tenant_access.require_tenant(device.tenant_id, principal.bearer_token)
    return device_to_admin_dict(device)


@router.post("/device/heartbeat")
def heartbeat(payload: HeartbeatInput, request: Request, session: Session = Depends(get_db), principal: DevicePrincipal = Depends(current_device_principal)):
    now = datetime.now(UTC)
    if payload.sent_at < now - timedelta(minutes=10) or payload.sent_at > now + timedelta(minutes=2):
        raise GuardianError(422, "heartbeat_clock_skew", "Heartbeat timestamp is outside the accepted clock window")
    try:
        outcome = apply_heartbeat(session, principal, payload, now)
    except DeviceBindingConflict as exc:
        session.rollback()
        raise GuardianError(409, "device_binding_conflict", str(exc)) from exc
    except DeviceDisabled as exc:
        session.rollback()
        raise GuardianError(403, "device_disabled", str(exc)) from exc
    session.commit()
    HEARTBEATS.inc()
    return {"device_id": str(principal.device_id), "server_time": now.isoformat(), "state": outcome.state, "heartbeat_interval_seconds": request.app.state.settings.heartbeat_interval_seconds, "command_poll_interval_seconds": request.app.state.settings.command_poll_interval_seconds}


@internal_router.get("/devices/{device_id}")
def internal_device(device_id: UUID, request: Request, session: Session = Depends(get_db)):
    token = request.headers.get("X-Guardian-Internal-Token", "")
    if not request.app.state.settings.trusted_proxy_token or token != request.app.state.settings.trusted_proxy_token:
        raise GuardianError(401, "internal_auth_required", "Internal authentication is required")
    device = session.get(DeviceSession, device_id)
    if device is None:
        raise GuardianError(404, "device_not_found", "Device not found")
    return {"device_id": str(device.device_id), "tenant_id": str(device.tenant_id), "guardian_asset_id": str(device.guardian_asset_id), "state": device.state, "agent_version": device.agent_version, "last_seen_at": device.last_seen_at.isoformat()}
