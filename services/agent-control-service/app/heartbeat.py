from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from .models import DeviceCapabilitySnapshot, DeviceSession
from .principal import DevicePrincipal
from .schemas import HeartbeatInput


class DeviceBindingConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HeartbeatOutcome:
    state: str
    online_transition: bool
    capabilities_changed: bool


def _normalize_capabilities(values: list[str]) -> list[str]:
    return sorted(set(values))


def apply_heartbeat(
    session: Session,
    principal: DevicePrincipal,
    payload: HeartbeatInput,
    now: datetime,
) -> HeartbeatOutcome:
    normalized = _normalize_capabilities(payload.capabilities)
    current = session.get(DeviceSession, principal.device_id)

    if current is None:
        current = DeviceSession(
            device_id=principal.device_id,
            tenant_id=principal.tenant_id,
            guardian_asset_id=principal.guardian_asset_id,
            certificate_serial=principal.certificate_serial,
            session_id=payload.session_id,
            state="online",
            agent_version=payload.agent_version,
            platform=payload.platform,
            platform_version=payload.platform_version,
            current_capabilities=normalized,
            capability_version=payload.capability_version,
            last_seen_at=now,
        )
        session.add(current)
        session.flush()
        session.add(
            DeviceCapabilitySnapshot(
                device_id=principal.device_id,
                capability_version=payload.capability_version,
                capabilities=normalized,
                created_at=now,
            )
        )
        session.flush()
        return HeartbeatOutcome(state="online", online_transition=True, capabilities_changed=True)

    if current.tenant_id != principal.tenant_id or current.guardian_asset_id != principal.guardian_asset_id:
        raise DeviceBindingConflict("device_id is already bound to another tenant or asset")

    online_transition = current.state != "online"
    capabilities_changed = current.current_capabilities != normalized

    current.certificate_serial = principal.certificate_serial
    current.session_id = payload.session_id
    current.state = "online"
    current.agent_version = payload.agent_version
    current.platform = payload.platform
    current.platform_version = payload.platform_version
    current.capability_version = payload.capability_version
    current.last_seen_at = now

    if capabilities_changed:
        current.current_capabilities = normalized
        session.add(
            DeviceCapabilitySnapshot(
                device_id=principal.device_id,
                capability_version=payload.capability_version,
                capabilities=normalized,
                created_at=now,
            )
        )

    session.flush()
    return HeartbeatOutcome(
        state="online",
        online_transition=online_transition,
        capabilities_changed=capabilities_changed,
    )
