from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from app.database import Base
from app.main import create_app
from app.models import DeviceEnrollment, EnrollmentStatus, EnrollmentToken, OutboxEvent
from app.pki_client import PKICertificateResult
from app.tokens import hash_token


def _seed() -> str:
    return base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode("ascii")


def _csr() -> tuple[ec.EllipticCurvePrivateKey, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "WS-SPS-001")]))
        .sign(key, hashes.SHA256())
    )
    return key, csr.public_bytes(serialization.Encoding.PEM).decode("ascii")


class FakePKIClient:
    def __init__(self) -> None:
        self.calls = []

    def issue(self, **kwargs) -> PKICertificateResult:
        self.calls.append(kwargs)
        now = datetime.now(UTC)
        return PKICertificateResult(
            certificate_id="cert-1",
            issuance_id=kwargs["issuance_id"],
            tenant_id=kwargs["tenant_id"],
            asset_id=kwargs["asset_id"],
            device_id=kwargs["device_id"],
            serial_hex="01AB",
            fingerprint_sha256="f" * 64,
            certificate_pem="CERTIFICATE-PUBLIC-MATERIAL",
            ca_chain_pem="CA-CHAIN-PUBLIC-MATERIAL",
            not_before=now - timedelta(minutes=1),
            not_after=now + timedelta(days=30),
        )


def _app(tmp_path):
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'enrollment-api.db'}",
        signing_key=_seed(),
    )
    Base.metadata.create_all(app.state.engine)
    app.state.pki_client = FakePKIClient()
    return app


def _seed_token(app, plaintext: str) -> str:
    with app.state.session_factory() as session:
        token = EnrollmentToken(
            token_hash=hash_token(plaintext),
            token_hint="gdt_api...test",
            tenant_id="tenant-1",
            asset_id="asset-1",
            created_by_user_id="admin-1",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(token)
        session.commit()
        session.refresh(token)
        return token.id


def test_endpoint_enrollment_reserves_calls_pki_and_finalizes_transactionally(tmp_path):
    app = _app(tmp_path)
    plaintext = "gdt_api_test_token_abcdefghijklmnopqrstuvwxyz0123456789"
    token_id = _seed_token(app, plaintext)
    endpoint_key, csr_pem = _csr()

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/enrollments",
            json={
                "token": plaintext,
                "platform": "windows",
                "hostname": "WS-SPS-001",
                "agent_version": "0.7.0-dev.1",
                "csr_pem": csr_pem,
            },
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "enrolled"
    assert body["device_id"]
    assert body["tenant_id"] == "tenant-1"
    assert body["asset_id"] == "asset-1"
    assert body["certificate_id"] == "cert-1"
    assert body["certificate_pem"] == "CERTIFICATE-PUBLIC-MATERIAL"
    assert body["ca_chain_pem"] == "CA-CHAIN-PUBLIC-MATERIAL"
    assert "grant" not in body
    assert "token" not in body
    assert plaintext not in response.text

    assert len(app.state.pki_client.calls) == 1
    pki_call = app.state.pki_client.calls[0]
    assert pki_call["tenant_id"] == "tenant-1"
    assert pki_call["asset_id"] == "asset-1"
    assert pki_call["device_id"] == body["device_id"]
    assert pki_call["issuance_id"]
    assert pki_call["csr_pem"] == csr_pem
    assert pki_call["grant"]

    with app.state.session_factory() as session:
        token = session.get(EnrollmentToken, token_id)
        enrollment = session.query(DeviceEnrollment).one()
        assert token.consumed_at is not None
        assert token.consumed_device_id == enrollment.device_id
        assert token.reserved_enrollment_id == enrollment.id
        assert enrollment.status == EnrollmentStatus.ENROLLED
        assert enrollment.certificate_id == "cert-1"
        assert enrollment.certificate_serial_hex == "01AB"
        assert enrollment.certificate_fingerprint_sha256 == "f" * 64
        assert enrollment.enrolled_at is not None
        event = session.query(OutboxEvent).one()
        assert event.event_type == "device.enrolled"
        assert event.aggregate_id == enrollment.device_id
        serialized = str(event.payload)
        assert plaintext not in serialized
        assert csr_pem not in serialized
        assert pki_call["grant"] not in serialized


def test_identical_retry_after_consumption_returns_same_result_without_calling_pki_again(tmp_path):
    app = _app(tmp_path)
    plaintext = "gdt_retry_test_token_abcdefghijklmnopqrstuvwxyz0123456789"
    _seed_token(app, plaintext)
    _, csr_pem = _csr()
    payload = {
        "token": plaintext,
        "platform": "windows",
        "hostname": "WS-SPS-001",
        "agent_version": "0.7.0-dev.1",
        "csr_pem": csr_pem,
    }

    with TestClient(app) as client:
        first = client.post("/api/v1/enrollments", json=payload)
        second = client.post("/api/v1/enrollments", json=payload)

    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert len(app.state.pki_client.calls) == 1

    with app.state.session_factory() as session:
        assert session.query(DeviceEnrollment).count() == 1
        assert session.query(OutboxEvent).filter(OutboxEvent.event_type == "device.enrolled").count() == 1


def test_consumed_token_with_different_csr_is_rejected_as_replay(tmp_path):
    app = _app(tmp_path)
    plaintext = "gdt_replay_test_token_abcdefghijklmnopqrstuvwxyz0123456789"
    _seed_token(app, plaintext)
    _, csr_one = _csr()
    _, csr_two = _csr()

    with TestClient(app) as client:
        first = client.post(
            "/api/v1/enrollments",
            json={"token": plaintext, "platform": "windows", "hostname": "WS-SPS-001", "csr_pem": csr_one},
        )
        replay = client.post(
            "/api/v1/enrollments",
            json={"token": plaintext, "platform": "windows", "hostname": "WS-SPS-001", "csr_pem": csr_two},
        )

    assert first.status_code == 201, first.text
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "enrollment.token_replay"
    assert len(app.state.pki_client.calls) == 1
