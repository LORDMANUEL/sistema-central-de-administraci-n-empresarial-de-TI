from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.database import Base, build_engine, build_session_factory
from app.models import DeviceEnrollment, EnrollmentStatus, EnrollmentToken, OutboxEvent


def _factory(tmp_path):
    engine = build_engine(f"sqlite+pysqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(engine)
    return engine, build_session_factory(engine)


def _token(**overrides):
    now = datetime.now(UTC)
    values = {
        "token_hash": "a" * 64,
        "token_hint": "gdt_abcd...wxyz",
        "tenant_id": "tenant-1",
        "asset_id": "asset-1",
        "created_by_user_id": "user-1",
        "expires_at": now + timedelta(hours=1),
    }
    values.update(overrides)
    return EnrollmentToken(**values)


def _enrollment(token_id: str, **overrides):
    values = {
        "device_id": "device-1",
        "token_id": token_id,
        "tenant_id": "tenant-1",
        "asset_id": "asset-1",
        "platform": "windows",
        "hostname": "WS-001",
        "agent_version": "0.7.0-dev.1",
        "csr_sha256": "b" * 64,
        "request_fingerprint": "c" * 64,
        "issuance_id": "11111111-1111-1111-1111-111111111111",
    }
    values.update(overrides)
    return DeviceEnrollment(**values)


def test_token_defaults_are_unreserved_unconsumed_and_unrevoked(tmp_path):
    engine, factory = _factory(tmp_path)
    try:
        with factory() as session:
            token = _token()
            session.add(token)
            session.commit()
            session.refresh(token)
            assert token.id
            assert token.created_at is not None
            assert token.reserved_at is None
            assert token.reserved_enrollment_id is None
            assert token.consumed_at is None
            assert token.consumed_device_id is None
            assert token.revoked_at is None
    finally:
        engine.dispose()


def test_token_hash_is_unique(tmp_path):
    engine, factory = _factory(tmp_path)
    try:
        with factory() as session:
            session.add(_token())
            session.commit()
        with factory() as session:
            session.add(_token())
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


def test_device_enrollment_defaults_pending_and_one_per_token(tmp_path):
    engine, factory = _factory(tmp_path)
    try:
        with factory() as session:
            token = _token()
            session.add(token)
            session.flush()
            first = _enrollment(token.id)
            session.add(first)
            session.commit()
            session.refresh(first)
            assert first.id
            assert first.status == EnrollmentStatus.PENDING
            assert first.certificate_id is None
            assert first.enrolled_at is None

        with factory() as session:
            second = _enrollment(
                token.id,
                device_id="device-2",
                issuance_id="22222222-2222-2222-2222-222222222222",
            )
            session.add(second)
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("field", "duplicate_value"),
    [
        ("device_id", "device-1"),
        ("issuance_id", "11111111-1111-1111-1111-111111111111"),
    ],
)
def test_device_identity_fields_are_unique(tmp_path, field, duplicate_value):
    engine, factory = _factory(tmp_path)
    try:
        with factory() as session:
            token1 = _token(token_hash="1" * 64)
            token2 = _token(token_hash="2" * 64)
            session.add_all([token1, token2])
            session.flush()
            session.add(_enrollment(token1.id))
            session.commit()
            second = _enrollment(
                token2.id,
                device_id="device-2",
                issuance_id="22222222-2222-2222-2222-222222222222",
            )
            setattr(second, field, duplicate_value)
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
                event_type="device.enrolled",
                aggregate_type="device",
                aggregate_id="device-1",
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
