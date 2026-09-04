from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import DeviceSession


def list_visible_devices(
    session: Session,
    accessible_tenant_ids: set[UUID],
    *,
    tenant_id: UUID | None,
    state: str | None,
    limit: int,
) -> list[DeviceSession]:
    if tenant_id is not None and tenant_id not in accessible_tenant_ids:
        return []
    tenant_ids = {tenant_id} if tenant_id is not None else accessible_tenant_ids
    if not tenant_ids:
        return []
    statement = select(DeviceSession).where(DeviceSession.tenant_id.in_(tenant_ids))
    if state is not None:
        statement = statement.where(DeviceSession.state == state)
    statement = statement.order_by(DeviceSession.last_seen_at.desc()).limit(max(1, min(limit, 500)))
    return list(session.scalars(statement).all())


def device_to_admin_dict(device: DeviceSession) -> dict:
    return {
        "device_id": str(device.device_id),
        "tenant_id": str(device.tenant_id),
        "guardian_asset_id": str(device.guardian_asset_id),
        "session_id": str(device.session_id),
        "state": device.state,
        "agent_version": device.agent_version,
        "platform": device.platform,
        "platform_version": device.platform_version,
        "capabilities": list(device.current_capabilities),
        "capability_version": device.capability_version,
        "last_seen_at": device.last_seen_at.isoformat(),
    }
