from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient

from app.database import Base
from app.errors import GuardianError
from app.main import create_app
from app.models import DeviceEnrollment, EnrollmentStatus, EnrollmentToken, OutboxEvent
from app.pki_client import PKICertificateResult
from app.tokens import hash_token


def _seed() -> str:
    return base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode("ascii")


def _csr() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "WS-RECOVERY")]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode("ascii")


def _certificate(kwargs) -> PKICertificateResult:
    now = datetime.now(UTC)
    return PKICertificateResult(
        certificate_id="cert-recovery",
        issuance_id=kwargs["issuance_id"],
        tenant_id=kwargs["tenant_id"],
        asset_id=kwargs["asset_id"],
        device_id=kwargs["device_id"],
        serial_hex="AA01",
        fingerprint_sha256="d" * 64,
        certificate_pem="CERTIFICATE-RECOVERY",
        ca_chain_pem="CHAIN-RECOVERY",
        not_before=now - timedelta(minutes=1),
        not_after=now + timedelta(days=30),
    )


class SequencePKIClient:
    def __init__(self, outcomes) -> None:
        self.outcomes = list(outcomes)
        self.calls = []

    def issue(self, **kwargs):
        self.calls.append(kwargs.copy())
        outcome = self.outcomes.pop(0)
        if callable(outcome):
            return outcome(kwargs)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _app(tmp_path, outcomes):
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'recovery.db'}",
        signing_key=_seed(),
    )
    Base.metadata.create_all(app.state.engine)
    app.state.pki_client = SequencePKIClient(outcomes)
    return app


def _token(app, plaintext):
    with app.state.session_factory() as session:
        row = EnrollmentToken(
            token_hash=hash_token(plaintext),
            token_hint="gdt_rec...test",
            tenant_id="tenant-1",
            asset_id="asset-1",
            created_by_user_id="admin-1",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def _payload(token, csr):
    return {
        "token": token,
        "platform": "windows",
        "hostname": "WS-RECOVERY",
        "agent_version": "0.7.0-dev.1",
        "csr_pem": csr,
    }


def test_transient_pki_failure_keeps_reservation_and_retry_reuses_same_identity(tmp_path):
    unavailable = GuardianError(503, "enrollment.pki_unavailable", "PKI Service is unavailable")
    app = _app(tmp_path, [unavailable, _certificate])
    plaintext = "gdt_transient_recovery_abcdefghijklmnopqrstuvwxyz0123456789"
    token_id = _token(app, plaintext)
    payload = _payload(plaintext, _csr())

    with TestClient(app) as client:
        first = client.post("/api/v1/enrollments", json=payload)

    assert first.status_code == 503
    assert first.json()["error"]["code"] == "enrollment.pki_unavailable"
    with app.state.session_factory() as session:
        token = session.get(EnrollmentToken, token_id)
        enrollment = session.query(DeviceEnrollment).one()
        first_device_id = enrollment.device_id
        first_issuance_id = enrollment.issuance_id
        assert token.reserved_at is not None
        assert token.reserved_enrollment_id == enrollment.id
        assert token.consumed_at is None
        assert enrollment.status == EnrollmentStatus.PENDING
        assert enrollment.failure_code == "enrollment.pki_unavailable"

    with TestClient(app) as client:
        retry = client.post("/api/v1/enrollments", json=payload)

    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == "enrolled"
    assert retry.json()["device_id"] == first_device_id
    assert len(app.state.pki_client.calls) == 2
    assert {call["device_id"] for call in app.state.pki_client.calls} == {first_device_id}
    assert {call["issuance_id"] for call in app.state.pki_client.calls} == {first_issuance_id}
    with app.state.session_factory() as session:
        assert session.query(DeviceEnrollment).count() == 1
        assert session.query(OutboxEvent).filter(OutboxEvent.event_type == "device.enrollment.failed").count() == 0
        assert session.query(OutboxEvent).filter(OutboxEvent.event_type == "device.enrolled").count() == 1


def test_correctable_pki_rejection_releases_token_and_new_request_gets_new_identity(tmp_path):
    rejected = GuardianError(422, "enrollment.pki_rejected", "PKI rejected certificate request")
    app = _app(tmp_path, [rejected, _certificate])
    plaintext = "gdt_rejected_recovery_abcdefghijklmnopqrstuvwxyz0123456789"
    token_id = _token(app, plaintext)
    first_payload = _payload(plaintext, _csr())

    with TestClient(app) as client:
        first = client.post("/api/v1/enrollments", json=first_payload)

    assert first.status_code == 422
    with app.state.session_factory() as session:
        token = session.get(EnrollmentToken, token_id)
        failed = session.query(DeviceEnrollment).one()
        old_device_id = failed.device_id
        old_issuance_id = failed.issuance_id
        assert token.reserved_at is None
        assert token.reserved_enrollment_id is None
        assert token.consumed_at is None
        assert failed.status == EnrollmentStatus.FAILED
        assert failed.failure_code == "enrollment.pki_rejected"
        event = session.query(OutboxEvent).one()
        assert event.event_type == "device.enrollment.failed"
        assert event.payload["device_id"] == old_device_id
        assert "token" not in str(event.payload).lower()
        assert "csr" not in str(event.payload).lower()

    second_payload = _payload(plaintext, _csr())
    with TestClient(app) as client:
        second = client.post("/api/v1/enrollments", json=second_payload)

    assert second.status_code == 201, second.text
    assert second.json()["status"] == "enrolled"
    assert second.json()["device_id"] != old_device_id
    assert len(app.state.pki_client.calls) == 2
    assert app.state.pki_client.calls[1]["issuance_id"] != old_issuance_id
    with app.state.session_factory() as session:
        assert session.query(DeviceEnrollment).count() == 1
        final = session.query(DeviceEnrollment).one()
        assert final.status == EnrollmentStatus.ENROLLED
        assert final.device_id == second.json()["device_id"]
        assert session.query(OutboxEvent).filter(OutboxEvent.event_type == "device.enrollment.failed").count() == 1
        assert session.query(OutboxEvent).filter(OutboxEvent.event_type == "device.enrolled").count() == 1


def test_pki_issuance_conflict_keeps_same_reservation_and_never_rolls_identity(tmp_path):
    conflict = GuardianError(
        409,
        "enrollment.pki_issuance_conflict",
        "PKI issuance ID conflicts with existing certificate data",
    )
    app = _app(tmp_path, [conflict, conflict])
    plaintext = "gdt_conflict_recovery_abcdefghijklmnopqrstuvwxyz0123456789"
    token_id = _token(app, plaintext)
    payload = _payload(plaintext, _csr())

    with TestClient(app) as client:
        first = client.post("/api/v1/enrollments", json=payload)
    assert first.status_code == 409

    with app.state.session_factory() as session:
        token = session.get(EnrollmentToken, token_id)
        enrollment = session.query(DeviceEnrollment).one()
        device_id = enrollment.device_id
        issuance_id = enrollment.issuance_id
        assert token.reserved_at is not None
        assert enrollment.status == EnrollmentStatus.PENDING
        assert enrollment.failure_code == "enrollment.pki_issuance_conflict"

    with TestClient(app) as client:
        second = client.post("/api/v1/enrollments", json=payload)
    assert second.status_code == 409
    assert len(app.state.pki_client.calls) == 2
    assert {call["device_id"] for call in app.state.pki_client.calls} == {device_id}
    assert {call["issuance_id"] for call in app.state.pki_client.calls} == {issuance_id}
    with app.state.session_factory() as session:
        assert session.query(DeviceEnrollment).count() == 1
        assert session.query(OutboxEvent).filter(OutboxEvent.event_type == "device.enrollment.failed").count() == 0
