from datetime import datetime
from uuid import UUID

from .models import OutboxEvent


def device_event(event_type: str, *, tenant_id: UUID, asset_id: UUID, device_id: UUID, occurred_at: datetime, extra: dict | None = None) -> OutboxEvent:
    payload = {
        "tenant_id": str(tenant_id),
        "guardian_asset_id": str(asset_id),
        "device_id": str(device_id),
        "occurred_at": occurred_at.isoformat(),
    }
    if extra:
        payload.update(extra)
    return OutboxEvent(event_type=event_type, aggregate_id=str(device_id), payload=payload)
