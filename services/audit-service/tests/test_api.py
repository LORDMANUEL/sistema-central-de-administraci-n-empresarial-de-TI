from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.auth import IdentityAccessVerifier, TenantAccessDecision
from app.chain import AuditEntry, append_record
from app.config import Settings
from app.main import create_app
from app.models import Base

TENANT_ONE = "11111111-1111-1111-1111-111111111111"
TENANT_TWO = "22222222-2222-2222-2222-222222222222"


class TenantResolver:
    def __init__(self, allowed_tenant: str, role: str = "auditor") -> None:
        self.allowed_tenant = allowed_tenant
        self.role = role

    def resolve(self, tenant_id: str, user_id: str, bearer_token: str) -> TenantAccessDecision:
        return TenantAccessDecision(
            allowed=tenant_id == self.allowed_tenant,
            role=self.role if tenant_id == self.allowed_tenant else None,
            tenant_status="active",
        )


def build_app(tmp_path, identity_crypto, allowed_tenant=TENANT_ONE):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'audit-api.db'}"
    app = create_app(database_url=database_url)
    Base.metadata.create_all(app.state.engine)
    _, _, jwks = identity_crypto
    app.state.identity_verifier = IdentityAccessVerifier(
        Settings(database_url=database_url),
        jwks=jwks,
    )
    app.state.tenant_access_client = TenantResolver(allowed_tenant)
    return app


def seed(app):
    with app.state.session_factory() as session:
        first, _ = append_record(
            session,
            AuditEntry(
                tenant_id=TENANT_ONE,
                source_event_id="event-1",
                source_type="asset.created",
                source_service="asset",
                actor_user_id="user-1",
                actor_type="user",
                action="asset.created",
                resource_type="asset",
                resource_id="asset-1",
                outcome="success",
                request_id="req-1",
                occurred_at=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
                metadata={"hostname": "WS-001"},
            ),
        )
        second, _ = append_record(
            session,
            AuditEntry(
                tenant_id=TENANT_ONE,
                source_event_id="event-2",
                source_type="device.enrolled",
                source_service="enrollment",
                actor_user_id=None,
                actor_type="system",
                action="device.enrolled",
                resource_type="device",
                resource_id="device-1",
                outcome="success",
                request_id="req-2",
                occurred_at=datetime(2026, 8, 24, 12, 1, tzinfo=UTC),
                metadata={"hostname": "WS-001", "platform": "windows"},
            ),
        )
        other, _ = append_record(
            session,
            AuditEntry(
                tenant_id=TENANT_TWO,
                source_event_id="event-3",
                source_type="asset.created",
                source_service="asset",
                actor_user_id="user-2",
                actor_type="user",
                action="asset.created",
                resource_type="asset",
                resource_id="asset-2",
                outcome="success",
                request_id="req-3",
                occurred_at=datetime(2026, 8, 24, 12, 2, tzinfo=UTC),
                metadata={"hostname": "WS-002"},
            ),
        )
        session.commit()
        return first.id, second.id, other.id


def auth(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_tenant_auditor_lists_only_authorized_tenant_with_after_sequence(tmp_path, identity_crypto, make_identity_token):
    app = build_app(tmp_path, identity_crypto)
    seed(app)
    token = make_identity_token(role="viewer", user_id="auditor-1")
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/audit/records?tenant_id={TENANT_ONE}&after_sequence=1&limit=50",
            headers=auth(token),
        )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["sequence"] == 2
    assert body["items"][0]["tenant_id"] == TENANT_ONE
    assert body["items"][0]["source_type"] == "device.enrolled"
    assert body["items"][0]["record_hash"]
    assert body["next_after_sequence"] == 2


def test_platform_admin_can_read_global_view_across_tenants(tmp_path, identity_crypto, make_identity_token):
    app = build_app(tmp_path, identity_crypto)
    seed(app)
    token = make_identity_token(role="platform_admin", user_id="platform-1")
    with TestClient(app) as client:
        response = client.get("/api/v1/audit/records?limit=10", headers=auth(token))
    assert response.status_code == 200
    tenants = {item["tenant_id"] for item in response.json()["items"]}
    assert TENANT_ONE in tenants and TENANT_TWO in tenants


def test_cross_tenant_list_and_detail_are_denied(tmp_path, identity_crypto, make_identity_token):
    app = build_app(tmp_path, identity_crypto, allowed_tenant=TENANT_ONE)
    _, _, other_id = seed(app)
    token = make_identity_token(role="viewer", user_id="auditor-1")
    with TestClient(app) as client:
        listing = client.get(f"/api/v1/audit/records?tenant_id={TENANT_TWO}", headers=auth(token))
        detail = client.get(f"/api/v1/audit/records/{other_id}", headers=auth(token))
    assert listing.status_code == 403
    assert detail.status_code == 403


def test_detail_and_chain_verification_are_read_only(tmp_path, identity_crypto, make_identity_token):
    app = build_app(tmp_path, identity_crypto)
    first_id, _, _ = seed(app)
    token = make_identity_token(role="viewer", user_id="auditor-1")
    with TestClient(app) as client:
        detail = client.get(f"/api/v1/audit/records/{first_id}", headers=auth(token))
        verify = client.get(f"/api/v1/audit/verify?tenant_id={TENANT_ONE}", headers=auth(token))
        patch = client.patch(f"/api/v1/audit/records/{first_id}", json={"outcome": "failure"}, headers=auth(token))
        delete = client.delete(f"/api/v1/audit/records/{first_id}", headers=auth(token))
    assert detail.status_code == 200
    assert detail.json()["id"] == first_id
    assert verify.status_code == 200
    assert verify.json()["valid"] is True
    assert verify.json()["record_count"] == 2
    assert patch.status_code == 405
    assert delete.status_code == 405


def test_query_limit_is_bounded_at_500(tmp_path, identity_crypto, make_identity_token):
    app = build_app(tmp_path, identity_crypto)
    seed(app)
    token = make_identity_token(role="platform_admin")
    with TestClient(app) as client:
        response = client.get("/api/v1/audit/records?limit=501", headers=auth(token))
    assert response.status_code == 422
