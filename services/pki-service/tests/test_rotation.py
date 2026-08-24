from __future__ import annotations

from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from app.ca import initialize_ca
from app.certificates import parse_and_validate_csr
from app.database import Base
from app.grants import EnrollmentGrantVerifier
from app.main import create_app
from app.models import Certificate, CertificateStatus, OutboxEvent


def _csr(key, cn="WS-SPS-001") -> str:
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode("ascii")


def _app(tmp_path, jwks):
    paths = initialize_ca(tmp_path / "root", tmp_path / "online")
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'pki-rotation.db'}",
        ca_cert_path=str(paths.intermediate_cert),
        ca_key_path=str(paths.intermediate_key),
    )
    app.state.root_cert_path = str(paths.root_cert)
    app.state.grant_verifier = EnrollmentGrantVerifier(app.state.settings, jwks=jwks)
    Base.metadata.create_all(app.state.engine)
    return app


def _issue(client, make_grant):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr_pem = _csr(key)
    issuance_id = str(uuid4())
    csr_hash = parse_and_validate_csr(csr_pem).csr_sha256
    grant = make_grant(
        claims={
            "sub": "device-1",
            "tenant_id": "tenant-1",
            "asset_id": "asset-1",
            "device_id": "device-1",
            "issuance_id": issuance_id,
            "csr_sha256": csr_hash,
        }
    )
    response = client.post(
        "/api/v1/certificates/issue",
        json={
            "issuance_id": issuance_id,
            "tenant_id": "tenant-1",
            "asset_id": "asset-1",
            "device_id": "device-1",
            "platform": "windows",
            "subject_cn": "WS-SPS-001",
            "csr_pem": csr_pem,
        },
        headers={"Authorization": f"Bearer {grant}"},
    )
    assert response.status_code == 201, response.text
    return response.json(), key


def _rotation_payload(old_id: str, csr_pem: str, issuance_id: str, **overrides):
    payload = {
        "certificate_id": old_id,
        "issuance_id": issuance_id,
        "tenant_id": "tenant-1",
        "asset_id": "asset-1",
        "device_id": "device-1",
        "platform": "windows",
        "subject_cn": "WS-SPS-001",
        "csr_pem": csr_pem,
    }
    payload.update(overrides)
    return payload


def _rotation_grant(make_grant, payload):
    return make_grant(
        claims={
            "type": "certificate_rotate",
            "sub": payload["device_id"],
            "tenant_id": payload["tenant_id"],
            "asset_id": payload["asset_id"],
            "device_id": payload["device_id"],
            "issuance_id": payload["issuance_id"],
            "csr_sha256": parse_and_validate_csr(payload["csr_pem"]).csr_sha256,
        }
    )


def test_rotation_issues_new_certificate_then_supersedes_old_atomically(tmp_path, enrollment_crypto, make_grant):
    _, _, jwks = enrollment_crypto
    app = _app(tmp_path, jwks)

    with TestClient(app) as client:
        old, old_key = _issue(client, make_grant)
        new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        new_csr = _csr(new_key)
        payload = _rotation_payload(old["certificate_id"], new_csr, str(uuid4()))
        response = client.post(
            "/api/v1/certificates/rotate",
            json=payload,
            headers={"Authorization": f"Bearer {_rotation_grant(make_grant, payload)}"},
        )

    assert response.status_code == 201, response.text
    replacement = response.json()
    assert replacement["certificate_id"] != old["certificate_id"]
    assert replacement["status"] == "active"
    replacement_cert = x509.load_pem_x509_certificate(replacement["certificate_pem"].encode("ascii"))
    assert replacement_cert.public_key().public_numbers() == new_key.public_key().public_numbers()
    assert replacement_cert.public_key().public_numbers() != old_key.public_key().public_numbers()

    with app.state.session_factory() as session:
        old_row = session.get(Certificate, old["certificate_id"])
        new_row = session.get(Certificate, replacement["certificate_id"])
        assert old_row.status == CertificateStatus.REVOKED
        assert old_row.revocation_reason == "superseded"
        assert old_row.revoked_at is not None
        assert new_row.status == CertificateStatus.ACTIVE
        assert new_row.replaces_certificate_id == old_row.id
        events = session.query(OutboxEvent).filter(OutboxEvent.event_type == "pki.certificate.rotated").all()
        assert len(events) == 1
        assert events[0].payload["old_certificate_id"] == old_row.id
        assert events[0].payload["new_certificate_id"] == new_row.id


def test_rotation_identity_mismatch_leaves_old_certificate_active(tmp_path, enrollment_crypto, make_grant):
    _, _, jwks = enrollment_crypto
    app = _app(tmp_path, jwks)

    with TestClient(app) as client:
        old, _ = _issue(client, make_grant)
        new_csr = _csr(rsa.generate_private_key(public_exponent=65537, key_size=2048))
        payload = _rotation_payload(
            old["certificate_id"],
            new_csr,
            str(uuid4()),
            asset_id="different-asset",
        )
        response = client.post(
            "/api/v1/certificates/rotate",
            json=payload,
            headers={"Authorization": f"Bearer {_rotation_grant(make_grant, payload)}"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "pki.rotation_identity_mismatch"
    with app.state.session_factory() as session:
        old_row = session.get(Certificate, old["certificate_id"])
        assert old_row.status == CertificateStatus.ACTIVE
        assert old_row.revoked_at is None
        assert session.query(Certificate).count() == 1
        assert session.query(OutboxEvent).filter(OutboxEvent.event_type == "pki.certificate.rotated").count() == 0


def test_rotation_rejects_reuse_of_old_private_key(tmp_path, enrollment_crypto, make_grant):
    _, _, jwks = enrollment_crypto
    app = _app(tmp_path, jwks)

    with TestClient(app) as client:
        old, old_key = _issue(client, make_grant)
        reused_csr = _csr(old_key)
        payload = _rotation_payload(old["certificate_id"], reused_csr, str(uuid4()))
        response = client.post(
            "/api/v1/certificates/rotate",
            json=payload,
            headers={"Authorization": f"Bearer {_rotation_grant(make_grant, payload)}"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "pki.rotation_key_reuse"
    with app.state.session_factory() as session:
        assert session.get(Certificate, old["certificate_id"]).status == CertificateStatus.ACTIVE
        assert session.query(Certificate).count() == 1
