from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth import IdentityPrincipal
from app.errors import GuardianError
from app.main import create_app
from app.models import DeviceSession


class AuthStub:
    def verify(self, token: str):
        return IdentityPrincipal("user", "viewer", token)


class TenantAccessStub:
    def __init__(self, allowed):
        self.allowed = set(allowed)

    def accessible_tenant_ids(self, token: str):
        return set(self.allowed)

    def require_tenant(self, tenant_id, token: str):
        if tenant_id not in self.allowed:
            raise GuardianError(403, "agent_control.tenant_access_denied", "Tenant access denied")


def seed(app, tenant_id, state: str = "online") -> DeviceSession:
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
    with app.state.session_factory() as session:
        session.add(row)
        session.commit()
    return row


def test_devices_require_identity(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}")
    with TestClient(app) as client:
        assert client.get("/api/v1/devices").status_code == 401


def test_devices_list_only_accessible_tenants(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}")
    app.state.auth = AuthStub()
    tenant_a, tenant_b = uuid4(), uuid4()
    app.state.tenant_access = TenantAccessStub({tenant_a})
    visible = seed(app, tenant_a)
    seed(app, tenant_b)
    with TestClient(app) as client:
        response = client.get("/api/v1/devices", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert [item["device_id"] for item in response.json()] == [str(visible.device_id)]


def test_device_get_enforces_tenant_access(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}")
    app.state.auth = AuthStub()
    tenant_id = uuid4()
    row = seed(app, tenant_id)
    app.state.tenant_access = TenantAccessStub(set())
    with TestClient(app) as client:
        response = client.get(f"/api/v1/devices/{row.device_id}", headers={"Authorization": "Bearer x"})
        assert response.status_code == 403
