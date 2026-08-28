from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.admin import device_to_admin_dict, list_visible_devices
from app.models import Base, DeviceSession


def seed(session: Session, tenant_id, state: str = "online") -> DeviceSession:
    row = DeviceSession(
        device_id=uuid4(),
        tenant_id=tenant_id,
        guardian_asset_id=uuid4(),
        certificate_serial="A1",
        session_id=uuid4(),
        state=state,
        agent_version="0.7.0",
        platform="windows",
        platform_version="11",
        current_capabilities=["heartbeat.v1"],
        capability_version=1,
        last_seen_at=datetime.now(UTC),
    )
    session.add(row)
    session.commit()
    return row


def test_list_visible_devices_is_tenant_scoped():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tenant_a, tenant_b = uuid4(), uuid4()
    with Session(engine) as session:
        visible = seed(session, tenant_a)
        seed(session, tenant_b)
        rows = list_visible_devices(session, {tenant_a}, tenant_id=None, state=None, limit=100)
        assert [row.device_id for row in rows] == [visible.device_id]


def test_list_visible_devices_filters_state_and_limit():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tenant_id = uuid4()
    with Session(engine) as session:
        seed(session, tenant_id, "offline")
        online = seed(session, tenant_id, "online")
        rows = list_visible_devices(session, {tenant_id}, tenant_id=tenant_id, state="online", limit=1)
        assert [row.device_id for row in rows] == [online.device_id]


def test_device_to_admin_dict_contains_admin_state():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tenant_id = uuid4()
    with Session(engine) as session:
        row = seed(session, tenant_id)
        payload = device_to_admin_dict(row)
        assert payload["device_id"] == str(row.device_id)
        assert payload["tenant_id"] == str(tenant_id)
        assert payload["guardian_asset_id"] == str(row.guardian_asset_id)
        assert payload["state"] == "online"
        assert payload["platform"] == "windows"
        assert payload["capabilities"] == ["heartbeat.v1"]
