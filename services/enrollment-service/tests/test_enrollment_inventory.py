from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.auth import IdentityAccessVerifier, TenantAccessDecision
from app.database import Base
from app.main import create_app
from app.models import DeviceEnrollment, EnrollmentStatus, EnrollmentToken


def _seed() -> str:
    return base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode("ascii")


def _app(tmp_path, identity_jwks):
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'inventory.db'}",
        signing_key=_seed(),
    )
    Base.metadata.create_all(app.state.engine)
    app.state.identity_verifier = IdentityAccessVerifier(app.state.settings, jwks=identity_jwks)
    return app


def _seed_enrollment(app, *, tenant_id="tenant-1", device_id="device-1"):
    with app.state.session_factory() as session:
        token = EnrollmentToken(
            token_hash=("a" if tenant_id == "tenant-1" else "b") * 64,
            token_hint="gdt_inv...test",
            tenant_id=tenant_id,
            asset_id=f"asset-{tenant_id}",
            created_by_user_id="admin-1",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            reserved_at=datetime.now(UTC),
            consumed_at=datetime.now(UTC),
            consumed_device_id=device_id,
        )
        session.add(token)
        session.flush()
        enrollment = DeviceEnrollment(
            device_id=device_id,
            token_id=token.id,
            tenant_id=tenant_id,
            asset_id=f"asset-{tenant_id}",
            platform="windows",
            hostname=f"WS-{tenant_id}",
            agent_version="0.7.0-dev.1",
            csr_sha256="c" * 64,
            request_fingerprint="d" * 64,
            issuance_id=("1" if tenant_id == "tenant-1" else "2") * 36,
            status=EnrollmentStatus.ENROLLED,
            certificate_id=f"cert-{tenant_id}",
            certificate_serial_hex="01AB",
            certificate_fingerprint_sha256="e" * 64,
            certificate_pem="CERTIFICATE-PUBLIC-MATERIAL",
            ca_chain_pem="CA-CHAIN-PUBLIC-MATERIAL",
            certificate_not_before=datetime.now(UTC) - timedelta(minutes=1),
            certificate_not_after=datetime.now(UTC) + timedelta(days=30),
            enrolled_at=datetime.now(UTC),
        )
        session.add(enrollment)
        session.flush()
        token.reserved_enrollment_id = enrollment.id
        session.commit()
        return device_id


def test_platform_admin_lists_and_gets_enrollment_without_internal_secret_fields(
    tmp_path, identity_crypto, make_identity_token
):
    _, _, jwks = identity_crypto
    app = _app(tmp_path, jwks)
    device_id = _seed_enrollment(app)
    headers = {"Authorization": f"Bearer {make_identity_token(role='platform_admin')}"}

    with TestClient(app) as client:
        listed = client.get("/api/v1/enrollments", params={"tenant_id": "tenant-1"}, headers=headers)
        fetched = client.get(f"/api/v1/enrollments/{device_id}", headers=headers)

    assert listed.status_code == 200, listed.text
    assert fetched.status_code == 200, fetched.text
    assert len(listed.json()) == 1
    assert listed.json()[0] == fetched.json()
    body = fetched.json()
    assert body["device_id"] == device_id
    assert body["tenant_id"] == "tenant-1"
    assert body["status"] == "enrolled"
    assert body["certificate_id"] == "cert-tenant-1"
    for forbidden in (
        "token",
        "token_hash",
        "token_id",
        "request_fingerprint",
        "csr_sha256",
        "csr_pem",
        "certificate_pem",
        "ca_chain_pem",
    ):
        assert forbidden not in body
        assert forbidden not in fetched.text


def test_org_admin_can_read_only_its_active_tenant(tmp_path, identity_crypto, make_identity_token):
    _, _, jwks = identity_crypto
    app = _app(tmp_path, jwks)
    own_device = _seed_enrollment(app, tenant_id="tenant-1", device_id="device-1")
    other_device = _seed_enrollment(app, tenant_id="tenant-2", device_id="device-2")
    bearer = make_identity_token(role="viewer", user_id="org-operator")
    headers = {"Authorization": f"Bearer {bearer}"}

    def resolver(tenant_id, user_id, token):
        assert user_id == "org-operator"
        assert token == bearer
        if tenant_id == "tenant-1":
            return TenantAccessDecision(allowed=True, role="org_admin", tenant_status="active")
        return TenantAccessDecision(allowed=False, role=None, tenant_status="active")

    app.state.tenant_access_resolver = resolver

    with TestClient(app) as client:
        own_list = client.get("/api/v1/enrollments", params={"tenant_id": "tenant-1"}, headers=headers)
        own_get = client.get(f"/api/v1/enrollments/{own_device}", headers=headers)
        denied_list = client.get("/api/v1/enrollments", params={"tenant_id": "tenant-2"}, headers=headers)
        denied_get = client.get(f"/api/v1/enrollments/{other_device}", headers=headers)

    assert own_list.status_code == 200
    assert own_get.status_code == 200
    assert denied_list.status_code == 403
    assert denied_list.json()["error"]["code"] == "enrollment.access_denied"
    assert denied_get.status_code == 403
    assert denied_get.json()["error"]["code"] == "enrollment.access_denied"
