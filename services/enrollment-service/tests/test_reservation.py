from datetime import UTC, datetime, timedelta

import pytest

from app.database import Base, build_engine, build_session_factory
from app.errors import GuardianError
from app.models import DeviceEnrollment, EnrollmentStatus, EnrollmentToken
from app.reservation import EnrollmentRequestData, reserve_or_resume
from app.tokens import hash_token


def _database(tmp_path):
    engine = build_engine(f"sqlite+pysqlite:///{tmp_path / 'reservation.db'}")
    Base.metadata.create_all(engine)
    return engine, build_session_factory(engine)


def _seed_token(factory, plaintext="gdt_reservation_test_token_abcdefghijklmnopqrstuvwxyz", **overrides):
    now = datetime.now(UTC)
    values = {
        "token_hash": hash_token(plaintext),
        "token_hint": "gdt_res...wxyz",
        "tenant_id": "tenant-1",
        "asset_id": "asset-1",
        "created_by_user_id": "admin-1",
        "expires_at": now + timedelta(hours=1),
    }
    values.update(overrides)
    with factory() as session:
        token = EnrollmentToken(**values)
        session.add(token)
        session.commit()
        session.refresh(token)
        return token.id, plaintext


def _request(**overrides):
    values = {
        "platform": "windows",
        "hostname": "WS-SPS-001",
        "agent_version": "0.7.0-dev.1",
        "csr_sha256": "a" * 64,
    }
    values.update(overrides)
    return EnrollmentRequestData(**values)


def test_unknown_expired_and_revoked_tokens_do_not_create_enrollment(tmp_path):
    engine, factory = _database(tmp_path)
    try:
        with factory() as session:
            with pytest.raises(GuardianError) as raised:
                reserve_or_resume(session, "gdt_unknown", _request())
            assert raised.value.code == "enrollment.token_not_found"
            assert session.query(DeviceEnrollment).count() == 0

        expired_id, expired_plain = _seed_token(
            factory,
            plaintext="gdt_expired_abcdefghijklmnopqrstuvwxyz0123456789",
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        with factory() as session:
            with pytest.raises(GuardianError) as raised:
                reserve_or_resume(session, expired_plain, _request())
            assert raised.value.code == "enrollment.token_expired"
            assert session.query(DeviceEnrollment).count() == 0
            assert session.get(EnrollmentToken, expired_id).reserved_at is None

        revoked_id, revoked_plain = _seed_token(
            factory,
            plaintext="gdt_revoked_abcdefghijklmnopqrstuvwxyz0123456789",
            revoked_at=datetime.now(UTC),
        )
        with factory() as session:
            with pytest.raises(GuardianError) as raised:
                reserve_or_resume(session, revoked_plain, _request())
            assert raised.value.code == "enrollment.token_revoked"
            assert session.query(DeviceEnrollment).count() == 0
            assert session.get(EnrollmentToken, revoked_id).reserved_at is None
    finally:
        engine.dispose()


def test_first_redemption_reserves_token_and_creates_stable_pending_identity(tmp_path):
    engine, factory = _database(tmp_path)
    try:
        token_id, plaintext = _seed_token(factory)
        with factory() as session:
            result = reserve_or_resume(session, plaintext, _request())
            session.commit()
            assert result.resumed is False
            assert result.consumed is False
            assert result.enrollment.status == EnrollmentStatus.PENDING
            assert result.enrollment.device_id
            assert result.enrollment.issuance_id
            assert result.enrollment.tenant_id == "tenant-1"
            assert result.enrollment.asset_id == "asset-1"
            assert result.enrollment.token_id == token_id
            first_device_id = result.enrollment.device_id
            first_issuance_id = result.enrollment.issuance_id

        with factory() as session:
            token = session.get(EnrollmentToken, token_id)
            enrollment = session.query(DeviceEnrollment).one()
            assert token.reserved_at is not None
            assert token.reserved_enrollment_id == enrollment.id
            assert token.consumed_at is None
            assert enrollment.device_id == first_device_id
            assert enrollment.issuance_id == first_issuance_id
    finally:
        engine.dispose()


def test_identical_retry_while_reserved_resumes_same_device_and_issuance(tmp_path):
    engine, factory = _database(tmp_path)
    try:
        _, plaintext = _seed_token(factory)
        with factory() as session:
            first = reserve_or_resume(session, plaintext, _request())
            session.commit()
            device_id = first.enrollment.device_id
            issuance_id = first.enrollment.issuance_id

        with factory() as session:
            retry = reserve_or_resume(session, plaintext, _request())
            session.commit()
            assert retry.resumed is True
            assert retry.consumed is False
            assert retry.enrollment.device_id == device_id
            assert retry.enrollment.issuance_id == issuance_id
            assert session.query(DeviceEnrollment).count() == 1
    finally:
        engine.dispose()


def test_mismatched_retry_while_reserved_is_replay(tmp_path):
    engine, factory = _database(tmp_path)
    try:
        _, plaintext = _seed_token(factory)
        with factory() as session:
            reserve_or_resume(session, plaintext, _request())
            session.commit()

        with factory() as session:
            with pytest.raises(GuardianError) as raised:
                reserve_or_resume(session, plaintext, _request(csr_sha256="b" * 64))
            assert raised.value.code == "enrollment.token_replay"
            assert session.query(DeviceEnrollment).count() == 1
    finally:
        engine.dispose()


def test_reserved_retry_remains_resumable_after_original_token_expiry(tmp_path):
    engine, factory = _database(tmp_path)
    try:
        token_id, plaintext = _seed_token(factory)
        with factory() as session:
            first = reserve_or_resume(session, plaintext, _request())
            session.commit()
            device_id = first.enrollment.device_id

        with factory() as session:
            token = session.get(EnrollmentToken, token_id)
            token.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            session.commit()

        with factory() as session:
            retry = reserve_or_resume(session, plaintext, _request())
            assert retry.resumed is True
            assert retry.enrollment.device_id == device_id
    finally:
        engine.dispose()


def test_identical_consumed_retry_returns_existing_enrollment_but_mismatch_is_replay(tmp_path):
    engine, factory = _database(tmp_path)
    try:
        token_id, plaintext = _seed_token(factory)
        with factory() as session:
            first = reserve_or_resume(session, plaintext, _request())
            first.enrollment.status = EnrollmentStatus.ENROLLED
            first.enrollment.certificate_id = "cert-1"
            first.enrollment.enrolled_at = datetime.now(UTC)
            token = session.get(EnrollmentToken, token_id)
            token.consumed_at = datetime.now(UTC)
            token.consumed_device_id = first.enrollment.device_id
            session.commit()
            device_id = first.enrollment.device_id
            issuance_id = first.enrollment.issuance_id

        with factory() as session:
            retry = reserve_or_resume(session, plaintext, _request())
            assert retry.resumed is True
            assert retry.consumed is True
            assert retry.enrollment.device_id == device_id
            assert retry.enrollment.issuance_id == issuance_id

        with factory() as session:
            with pytest.raises(GuardianError) as raised:
                reserve_or_resume(session, plaintext, _request(hostname="OTHER-PC"))
            assert raised.value.code == "enrollment.token_replay"
            assert session.query(DeviceEnrollment).count() == 1
    finally:
        engine.dispose()
