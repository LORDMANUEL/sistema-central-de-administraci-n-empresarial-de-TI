from datetime import datetime
from uuid import UUID

from .models import OutboxEvent


def command_event(event_type: str, *, command_id: UUID, tenant_id: UUID, asset_id: UUID, device_id: UUID, occurred_at: datetime, extra: dict | None = None) -> OutboxEvent:
    payload = {"command_id": str(command_id), "tenant_id": str(tenant_id), "guardian_asset_id": str(asset_id), "device_id": str(device_id), "occurred_at": occurred_at.isoformat()}
    if extra:
        payload.update(extra)
    return OutboxEvent(subject=f"guardian.{event_type}", aggregate_id=str(command_id), payload=payload)


def command_wakeup(*, command_id: UUID, device_id: UUID, tenant_id: UUID, occurred_at: datetime) -> OutboxEvent:
    return OutboxEvent(subject=f"device.command.available.{device_id}", aggregate_id=str(command_id), payload={"command_id": str(command_id), "device_id": str(device_id), "tenant_id": str(tenant_id), "occurred_at": occurred_at.isoformat()})
