from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .events import device_event
from .models import DeviceSession


def mark_stale_devices_offline(session: Session, cutoff: datetime, now: datetime) -> list[UUID]:
    stale_devices = session.execute(select(DeviceSession).where(DeviceSession.state == "online", DeviceSession.last_seen_at < cutoff).order_by(DeviceSession.last_seen_at)).scalars().all()
    changed: list[UUID] = []
    for device in stale_devices:
        device.state = "offline"
        changed.append(device.device_id)
        session.add(device_event("device.offline", tenant_id=device.tenant_id, asset_id=device.guardian_asset_id, device_id=device.device_id, occurred_at=now))
    session.flush()
    return changed
