from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.heartbeat import apply_heartbeat
from app.models import DeviceSession
from app.offline import mark_stale_devices_offline
from app.principal import DevicePrincipal
from app.schemas import HeartbeatInput


def heartbeat_payload(sent_at: datetime) -> HeartbeatInput:
    return HeartbeatInput(
        session_id=uuid4(),
        agent_version="0.7.0-dev",
        platform="windows",
        platform_version="10.0.26100",
        capabilities=["inventory.basic"],
        capability_version=1,
        sent_at=sent_at,
    )


def test_stale_online_device_transitions_offline_once(session):
    now = datetime.now(UTC)
    principal = DevicePrincipal(uuid4(), uuid4(), uuid4(), "01AB")
    apply_heartbeat(session, principal, heartbeat_payload(now - timedelta(minutes=5)), now - timedelta(minutes=5))

    first = mark_stale_devices_offline(session, now - timedelta(minutes=3), now)
    second = mark_stale_devices_offline(session, now - timedelta(minutes=3), now)

    stored = session.get(DeviceSession, principal.device_id)
    assert first == [principal.device_id]
    assert second == []
    assert stored is not None
    assert stored.state == "offline"


def test_recent_device_remains_online(session):
    now = datetime.now(UTC)
    principal = DevicePrincipal(uuid4(), uuid4(), uuid4(), "01AB")
    apply_heartbeat(session, principal, heartbeat_payload(now), now)

    changed = mark_stale_devices_offline(session, now - timedelta(minutes=3), now)

    stored = session.get(DeviceSession, principal.device_id)
    assert changed == []
    assert stored is not None
    assert stored.state == "online"
