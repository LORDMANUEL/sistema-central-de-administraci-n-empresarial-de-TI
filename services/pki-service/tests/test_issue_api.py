from __future__ import annotations

from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from app.ca import initialize_ca
from app.certificates import parse_and_validate_csr
from app.database import Base
from app.grants import EnrollmentGrantVerifier
from app.main import create_app
from app.models import Certificate, OutboxEvent


def _csr(key, cn="WS-SPS-001") -> str:
    request = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
        .sign(key, hashes.SHA256())
    )
    return request.public_bytes(serialization.Encoding.PEM).decode("ascii")


def _app(tmp_path, jwks):
    paths = initialize_ca(tmp_path / "root", tmp_path / "online")
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'pki-api.db'}",
        ca_cert_path=str(paths.intermediate_cert),
        ca_key_path=str(paths.intermediate_key),
    )
    app.state.root_cert_path = str(paths.root_cert)
    app.state.grant_verifier = EnrollmentGrantVerifier(app.state.settings, jwks=jwks)
    Base.metadata.create_all(app.state.engine)
    return app, paths


def _payload(csr_pem: str, issuance_id: str, **overrides):
    payload = {
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


def _grant(make_grant, payload):
    csr_hash = parse_and_validate_csr(payload["csr_pem"]).csr_sha256
    return make_grant(
        claims={
            "sub": payload["device_id"],
            "tenant_id": payload["tenant_id"],
            "asset_id": payload["asset_id"],
            "device_id": payload["device_id"],
            "issuance_id": payload["issuance_id"],
            "csr_sha256": csr_hash,
        }
    )


def test_issue_signs_real_csr_persists_certificate_and_outbox(tmp_path, enrollment_crypto, make_grant):
    _, _, jwks = enrollment_crypto
    app, paths = _app(tmp_path, jwks)
    device_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    payload = _payload(_csr(device_key), str(uuid4()))
    grant = _grant(make_grant, payload)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/certificates/issue",
            json=payload,
            headers={"Authorization": f"Bearer {grant}"},
        )
    assert response.status_code == 201, response.text
    body = response.json()
    cert = x509.load_pem_x509_certificate(body["certificate_pem"].encode("ascii"))
    intermediate = x509.load_pem_x509_certificate(paths.intermediate_cert.read_bytes())
    intermediate.public_key().verify(
        cert.signature,
        cert.tbs_certificate_bytes,
        padding.PKCS1v15(),
        cert.signature_hash_algorithm,
    )
    assert cert.public_key().public_numbers() == device_key.public_key().public_numbers()
    assert body["issuance_id"] == payload["issuance_id"]
    assert body["tenant_id"] == "tenant-1"
    assert body["asset_id"] == "asset-1"
    assert body["device_id"] == "device-1"
    assert body["status"] == "active"
    assert "PRIVATE KEY" not in body["certificate_pem"]
    assert "BEGIN CERTIFICATE" in body["ca_chain_pem"]

    with app.state.session_factory() as session:
        assert session.query(Certificate).count() == 1
        event = session.query(OutboxEvent).one()
        assert event.event_type == "pki.certificate.issued"
        assert event.payload["issuance_id"] == payload["issuance_id"]
        assert "certificate_pem" not in event.payload


def test_identical_retry_returns_same_certificate_without_duplicate_event(tmp_path, enrollment_crypto, make_grant):
    _, _, jwks = enrollment_crypto
    app, _ = _app(tmp_path, jwks)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    payload = _payload(_csr(key), str(uuid4()))
    grant = _grant(make_grant, payload)
    headers = {"Authorization": f"Bearer {grant}"}

    with TestClient(app) as client:
        first = client.post("/api/v1/certificates/issue", json=payload, headers=headers)
        second = client.post("/api/v1/certificates/issue", json=payload, headers=headers)

    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert second.json()["certificate_id"] == first.json()["certificate_id"]
    assert second.json()["serial_hex"] == first.json()["serial_hex"]
    assert second.json()["certificate_pem"] == first.json()["certificate_pem"]
    with app.state.session_factory() as session:
        assert session.query(Certificate).count() == 1
        assert session.query(OutboxEvent).count() == 1


def test_same_issuance_id_with_different_bound_data_returns_conflict(tmp_path, enrollment_crypto, make_grant):
    _, _, jwks = enrollment_crypto
    app, _ = _app(tmp_path, jwks)
    issuance_id = str(uuid4())
    first = _payload(_csr(rsa.generate_private_key(public_exponent=65537, key_size=2048)), issuance_id)
    second = _payload(_csr(rsa.generate_private_key(public_exponent=65537, key_size=2048)), issuance_id)

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/certificates/issue",
            json=first,
            headers={"Authorization": f"Bearer {_grant(make_grant, first)}"},
        )
        conflict = client.post(
            "/api/v1/certificates/issue",
            json=second,
            headers={"Authorization": f"Bearer {_grant(make_grant, second)}"},
        )

    assert created.status_code == 201, created.text
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "pki.issuance_conflict"


def test_grant_binding_mismatch_is_rejected_before_persistence(tmp_path, enrollment_crypto, make_grant):
    _, _, jwks = enrollment_crypto
    app, _ = _app(tmp_path, jwks)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    payload = _payload(_csr(key), str(uuid4()))
    grant = make_grant(
        claims={
            "sub": "device-OTHER",
            "device_id": "device-OTHER",
            "tenant_id": payload["tenant_id"],
            "asset_id": payload["asset_id"],
            "issuance_id": payload["issuance_id"],
            "csr_sha256": parse_and_validate_csr(payload["csr_pem"]).csr_sha256,
        }
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/certificates/issue",
            json=payload,
            headers={"Authorization": f"Bearer {grant}"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "pki.grant_binding_mismatch"
    with app.state.session_factory() as session:
        assert session.query(Certificate).count() == 0
        assert session.query(OutboxEvent).count() == 0
