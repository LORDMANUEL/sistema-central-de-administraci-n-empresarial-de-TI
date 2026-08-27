from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.heartbeat import DeviceBindingConflict, apply_heartbeat
from app.models import DeviceCapabilitySnapshot, DeviceSession
from app.principal import DevicePrincipal
from app.schemas import HeartbeatInput


def make_payload(*, capabilities: list[str] | None = None, capability_version: int = 1) -> HeartbeatInput:
    return HeartbeatInput(
        session_id=uuid4(),
        agent_version="0.7.0-dev",
        platform="windows",
        platform_version="10.0.26100",
        capabilities=capabilities or ["inventory.basic"],
        capability_version=capability_version,
        sent_at=datetime.now(UTC),
    )


def test_first_heartbeat_transitions_device_online(session):
    principal = DevicePrincipal(uuid4(), uuid4(), uuid4(), "01AB")

    outcome = apply_heartbeat(session, principal, make_payload(), datetime.now(UTC))

    stored = session.get(DeviceSession, principal.device_id)
    assert stored is not None
    assert stored.state == "online"
    assert stored.tenant_id == principal.tenant_id
    assert stored.guardian_asset_id == principal.guardian_asset_id
    assert outcome.online_transition is True
    assert outcome.capabilities_changed is True
    assert outcome.state == "online"


def test_repeated_heartbeat_does_not_repeat_online_or_capability_transition(session):
    principal = DevicePrincipal(uuid4(), uuid4(), uuid4(), "01AB")
    now = datetime.now(UTC)
    payload = make_payload()

    apply_heartbeat(session, principal, payload, now)
    second = apply_heartbeat(session, principal, payload, now)

    assert second.online_transition is False
    assert second.capabilities_changed is False
    assert session.query(DeviceCapabilitySnapshot).count() == 1


def test_capability_change_creates_new_immutable_snapshot(session):
    principal = DevicePrincipal(uuid4(), uuid4(), uuid4(), "01AB")
    now = datetime.now(UTC)

    apply_heartbeat(session, principal, make_payload(), now)
    changed = apply_heartbeat(
        session,
        principal,
        make_payload(capabilities=["command.reboot", "inventory.basic", "inventory.basic"], capability_version=2),
        now,
    )

    snapshots = session.query(DeviceCapabilitySnapshot).order_by(DeviceCapabilitySnapshot.created_at).all()
    assert changed.capabilities_changed is True
    assert len(snapshots) == 2
    assert snapshots[-1].capabilities == ["command.reboot", "inventory.basic"]


def test_device_id_cannot_rebind_to_another_asset(session):
    tenant_id = uuid4()
    device_id = uuid4()
    first = DevicePrincipal(tenant_id, uuid4(), device_id, "01AB")
    second = DevicePrincipal(tenant_id, uuid4(), device_id, "01AB")

    apply_heartbeat(session, first, make_payload(), datetime.now(UTC))

    with pytest.raises(DeviceBindingConflict):
        apply_heartbeat(session, second, make_payload(), datetime.now(UTC))

    stored = session.get(DeviceSession, device_id)
    assert stored is not None
    assert stored.guardian_asset_id == first.guardian_asset_id
