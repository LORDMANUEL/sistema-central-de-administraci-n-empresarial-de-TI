from __future__ import annotations

from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from app.auth import IdentityAccessVerifier, TenantAccessDecision
from app.ca import initialize_ca
from app.certificates import parse_and_validate_csr
from app.database import Base
from app.grants import EnrollmentGrantVerifier
from app.main import create_app
from app.models import OutboxEvent


def _csr(key, cn="WS-SPS-001") -> str:
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode("ascii")


def _app(tmp_path, enrollment_jwks, identity_jwks):
    paths = initialize_ca(tmp_path / "root", tmp_path / "online")
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'pki-revoke.db'}",
        ca_cert_path=str(paths.intermediate_cert),
        ca_key_path=str(paths.intermediate_key),
    )
    app.state.root_cert_path = str(paths.root_cert)
    app.state.grant_verifier = EnrollmentGrantVerifier(app.state.settings, jwks=enrollment_jwks)
    app.state.identity_verifier = IdentityAccessVerifier(app.state.settings, jwks=identity_jwks)
    app.state.tenant_access_resolver = None
    Base.metadata.create_all(app.state.engine)
    return app, paths


def _issue(client, make_grant, *, tenant_id="tenant-1", asset_id="asset-1", device_id="device-1"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr_pem = _csr(key)
    issuance_id = str(uuid4())
    csr_hash = parse_and_validate_csr(csr_pem).csr_sha256
    grant = make_grant(
        claims={
            "sub": device_id,
            "tenant_id": tenant_id,
            "asset_id": asset_id,
            "device_id": device_id,
            "issuance_id": issuance_id,
            "csr_sha256": csr_hash,
        }
    )
    response = client.post(
        "/api/v1/certificates/issue",
        json={
            "issuance_id": issuance_id,
            "tenant_id": tenant_id,
            "asset_id": asset_id,
            "device_id": device_id,
            "platform": "windows",
            "subject_cn": "WS-SPS-001",
            "csr_pem": csr_pem,
        },
        headers={"Authorization": f"Bearer {grant}"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_ca_chain_is_public_and_contains_intermediate_then_root(tmp_path, enrollment_crypto, identity_crypto):
    _, _, enrollment_jwks = enrollment_crypto
    _, _, identity_jwks = identity_crypto
    app, paths = _app(tmp_path, enrollment_jwks, identity_jwks)

    with TestClient(app) as client:
        response = client.get("/api/v1/ca/chain")

    assert response.status_code == 200
    certificates = x509.load_pem_x509_certificates(response.content)
    assert len(certificates) == 2
    expected_intermediate = x509.load_pem_x509_certificate(paths.intermediate_cert.read_bytes())
    expected_root = x509.load_pem_x509_certificate(paths.root_cert.read_bytes())
    assert certificates[0].fingerprint(hashes.SHA256()) == expected_intermediate.fingerprint(hashes.SHA256())
    assert certificates[1].fingerprint(hashes.SHA256()) == expected_root.fingerprint(hashes.SHA256())
    assert "private" not in response.text.lower()


def test_platform_admin_lists_gets_and_revokes_certificate_idempotently(
    tmp_path, enrollment_crypto, identity_crypto, make_grant, make_identity_token
):
    _, _, enrollment_jwks = enrollment_crypto
    _, _, identity_jwks = identity_crypto
    app, _ = _app(tmp_path, enrollment_jwks, identity_jwks)
    admin_headers = {"Authorization": f"Bearer {make_identity_token(role='platform_admin')}"}

    with TestClient(app) as client:
        issued = _issue(client, make_grant)
        listed = client.get("/api/v1/certificates", params={"tenant_id": "tenant-1"}, headers=admin_headers)
        fetched = client.get(f"/api/v1/certificates/{issued['certificate_id']}", headers=admin_headers)
        revoked = client.post(
            f"/api/v1/certificates/{issued['certificate_id']}/revoke",
            json={"reason": "key_compromise"},
            headers=admin_headers,
        )
        again = client.post(
            f"/api/v1/certificates/{issued['certificate_id']}/revoke",
            json={"reason": "key_compromise"},
            headers=admin_headers,
        )

    assert listed.status_code == 200, listed.text
    assert [item["certificate_id"] for item in listed.json()] == [issued["certificate_id"]]
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["certificate_id"] == issued["certificate_id"]
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == "revoked"
    assert revoked.json()["revocation_reason"] == "key_compromise"
    assert revoked.json()["revoked_at"] is not None
    assert again.status_code == 200, again.text
    assert again.json()["revoked_at"] == revoked.json()["revoked_at"]

    with app.state.session_factory() as session:
        events = session.query(OutboxEvent).filter(OutboxEvent.event_type == "pki.certificate.revoked").all()
        assert len(events) == 1
        assert events[0].payload["reason"] == "key_compromise"


def test_signed_crl_contains_revoked_serial(tmp_path, enrollment_crypto, identity_crypto, make_grant, make_identity_token):
    _, _, enrollment_jwks = enrollment_crypto
    _, _, identity_jwks = identity_crypto
    app, paths = _app(tmp_path, enrollment_jwks, identity_jwks)
    admin_headers = {"Authorization": f"Bearer {make_identity_token(role='platform_admin')}"}

    with TestClient(app) as client:
        issued = _issue(client, make_grant)
        revoked = client.post(
            f"/api/v1/certificates/{issued['certificate_id']}/revoke",
            json={"reason": "key_compromise"},
            headers=admin_headers,
        )
        assert revoked.status_code == 200, revoked.text
        crl_response = client.get("/api/v1/ca/crl")

    assert crl_response.status_code == 200, crl_response.text
    crl = x509.load_pem_x509_crl(crl_response.content)
    intermediate = x509.load_pem_x509_certificate(paths.intermediate_cert.read_bytes())
    intermediate.public_key().verify(
        crl.signature,
        crl.tbs_certlist_bytes,
        padding.PKCS1v15(),
        crl.signature_hash_algorithm,
    )
    assert crl.issuer == intermediate.subject
    revoked_serials = {entry.serial_number for entry in crl}
    assert int(issued["serial_hex"], 16) in revoked_serials
    assert crl.next_update_utc > crl.last_update_utc


def test_org_admin_scope_is_resolved_through_tenant_service_contract(
    tmp_path, enrollment_crypto, identity_crypto, make_grant, make_identity_token
):
    _, _, enrollment_jwks = enrollment_crypto
    _, _, identity_jwks = identity_crypto
    app, _ = _app(tmp_path, enrollment_jwks, identity_jwks)
    token = make_identity_token(role="viewer", user_id="org-operator")
    headers = {"Authorization": f"Bearer {token}"}

    def resolver(tenant_id: str, user_id: str, bearer_token: str) -> TenantAccessDecision:
        assert user_id == "org-operator"
        assert bearer_token == token
        if tenant_id == "tenant-1":
            return TenantAccessDecision(allowed=True, role="org_admin", tenant_status="active")
        return TenantAccessDecision(allowed=False, role=None, tenant_status="active")

    app.state.tenant_access_resolver = resolver

    with TestClient(app) as client:
        issued = _issue(client, make_grant, tenant_id="tenant-1")
        allowed = client.get("/api/v1/certificates", params={"tenant_id": "tenant-1"}, headers=headers)
        denied = client.get("/api/v1/certificates", params={"tenant_id": "tenant-2"}, headers=headers)
        fetched = client.get(f"/api/v1/certificates/{issued['certificate_id']}", headers=headers)

    assert allowed.status_code == 200, allowed.text
    assert len(allowed.json()) == 1
    assert fetched.status_code == 200, fetched.text
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "pki.access_denied"
