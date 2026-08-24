from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import Base, build_engine, build_session_factory
from app.models import Certificate, CertificateStatus, OutboxEvent


def _factory(tmp_path):
    engine = build_engine(f"sqlite+pysqlite:///{tmp_path / 'pki-models.db'}")
    Base.metadata.create_all(engine)
    return engine, build_session_factory(engine)


def _certificate(**overrides):
    now = datetime.now(UTC)
    values = {
        "issuance_id": "11111111-1111-1111-1111-111111111111",
        "tenant_id": "tenant-1",
        "asset_id": "asset-1",
        "device_id": "device-1",
        "platform": "windows",
        "serial_hex": "01AB",
        "csr_sha256": "a" * 64,
        "fingerprint_sha256": "b" * 64,
        "subject_cn": "WS-SPS-001",
        "san_uri": "spiffe://guardian/tenant/tenant-1/asset/asset-1/device/device-1",
        "certificate_pem": "-----BEGIN CERTIFICATE-----\nTEST\n-----END CERTIFICATE-----\n",
        "not_before": now - timedelta(minutes=1),
        "not_after": now + timedelta(days=30),
    }
    values.update(overrides)
    return Certificate(**values)


def test_certificate_defaults_active_and_unrevoked(tmp_path):
    engine, factory = _factory(tmp_path)
    try:
        with factory() as session:
            cert = _certificate()
            session.add(cert)
            session.commit()
            session.refresh(cert)
            assert cert.id
            assert cert.status == CertificateStatus.ACTIVE
            assert cert.revoked_at is None
            assert cert.revocation_reason is None
            assert cert.replaces_certificate_id is None
            assert cert.issued_at is not None
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("issuance_id", "11111111-1111-1111-1111-111111111111"),
        ("serial_hex", "01AB"),
        ("fingerprint_sha256", "b" * 64),
    ],
)
def test_certificate_identity_fields_are_unique(tmp_path, field, value):
    engine, factory = _factory(tmp_path)
    try:
        with factory() as session:
            session.add(_certificate())
            session.commit()

        second = _certificate(
            issuance_id="22222222-2222-2222-2222-222222222222",
            serial_hex="02CD",
            fingerprint_sha256="c" * 64,
        )
        setattr(second, field, value)
        with factory() as session:
            session.add(second)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_outbox_has_resilient_delivery_state(tmp_path):
    engine, factory = _factory(tmp_path)
    try:
        with factory() as session:
            event = OutboxEvent(
                event_type="pki.certificate.issued",
                aggregate_type="certificate",
                aggregate_id="cert-1",
                payload={"tenant_id": "tenant-1"},
            )
            session.add(event)
            session.commit()
            session.refresh(event)
            assert event.event_id
            assert event.attempts == 0
            assert event.last_error is None
            assert event.published_at is None
            assert event.created_at is not None
    finally:
        engine.dispose()
