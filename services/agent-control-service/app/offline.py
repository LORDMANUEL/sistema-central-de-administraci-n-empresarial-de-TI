from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import DeviceSession


def mark_stale_devices_offline(
    session: Session,
    cutoff: datetime,
    now: datetime,
) -> list[UUID]:
    """Transition stale online devices to offline exactly once.

    The caller owns the surrounding transaction. `now` is part of the
    stable domain interface so a later outbox/state-changed timestamp can
    be added without changing callers.
    """
    _ = now
    stale_devices = session.execute(
        select(DeviceSession)
        .where(
            DeviceSession.state == "online",
            DeviceSession.last_seen_at < cutoff,
        )
        .order_by(DeviceSession.last_seen_at, DeviceSession.device_id)
    ).scalars().all()

    changed: list[UUID] = []
    for device in stale_devices:
        device.state = "offline"
        changed.append(device.device_id)

    session.flush()
    return changed
