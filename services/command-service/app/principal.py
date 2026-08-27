from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DevicePrincipal:
    tenant_id: UUID
    guardian_asset_id: UUID
    device_id: UUID
    certificate_serial: str
