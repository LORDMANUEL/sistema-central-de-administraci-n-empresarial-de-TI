from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .errors import GuardianError
from .models import DeviceEnrollment, EnrollmentToken
from .tokens import hash_token, request_fingerprint


@dataclass(frozen=True)
class EnrollmentRequestData:
    platform: str
    hostname: str
    agent_version: str | None
    csr_sha256: str


@dataclass(frozen=True)
class ReservationResult:
    token: EnrollmentToken
    enrollment: DeviceEnrollment
    resumed: bool
    consumed: bool


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _find_enrollment(session: Session, token: EnrollmentToken) -> DeviceEnrollment:
    enrollment = None
    if token.reserved_enrollment_id:
        enrollment = session.get(DeviceEnrollment, token.reserved_enrollment_id)
    if enrollment is None:
        enrollment = session.scalar(
            select(DeviceEnrollment).where(DeviceEnrollment.token_id == token.id)
        )
    if enrollment is None:
        raise GuardianError(
            409,
            "enrollment.state_inconsistent",
            "Enrollment token state is inconsistent",
        )
    return enrollment


def _fingerprint(token: EnrollmentToken, request_data: EnrollmentRequestData) -> str:
    return request_fingerprint(
        tenant_id=token.tenant_id,
        asset_id=token.asset_id,
        csr_sha256=request_data.csr_sha256,
        platform=request_data.platform,
        hostname=request_data.hostname,
        agent_version=request_data.agent_version,
    )


def _resume_or_replay(
    session: Session,
    token: EnrollmentToken,
    request_data: EnrollmentRequestData,
    *,
    consumed: bool,
) -> ReservationResult:
    enrollment = _find_enrollment(session, token)
    if enrollment.request_fingerprint != _fingerprint(token, request_data):
        raise GuardianError(
            409,
            "enrollment.token_replay",
            "Enrollment token is already bound to a different request",
        )
    return ReservationResult(
        token=token,
        enrollment=enrollment,
        resumed=True,
        consumed=consumed,
    )


def reserve_or_resume(
    session: Session,
    token_plaintext: str,
    request_data: EnrollmentRequestData,
    *,
    now: datetime | None = None,
) -> ReservationResult:
    current_time = now or datetime.now(UTC)
    token = session.scalar(
        select(EnrollmentToken)
        .where(EnrollmentToken.token_hash == hash_token(token_plaintext))
        .with_for_update()
    )
    if token is None:
        raise GuardianError(404, "enrollment.token_not_found", "Enrollment token not found")

    # A completed enrollment remains retrievable by an identical retry even if
    # the token is later expired/revoked; no new authority is granted because
    # the request fingerprint and device identity must already match.
    if token.consumed_at is not None:
        return _resume_or_replay(session, token, request_data, consumed=True)

    if token.revoked_at is not None:
        raise GuardianError(409, "enrollment.token_revoked", "Enrollment token has been revoked")

    # Once a valid request reserved the token, transient downstream failures
    # must remain recoverable with the same identity even after original TTL.
    if token.reserved_at is not None or token.reserved_enrollment_id is not None:
        return _resume_or_replay(session, token, request_data, consumed=False)

    if _utc(token.expires_at) <= _utc(current_time):
        raise GuardianError(409, "enrollment.token_expired", "Enrollment token has expired")

    fingerprint = _fingerprint(token, request_data)
    enrollment = DeviceEnrollment(
        device_id=str(uuid4()),
        token_id=token.id,
        tenant_id=token.tenant_id,
        asset_id=token.asset_id,
        platform=request_data.platform.strip().lower(),
        hostname=request_data.hostname.strip(),
        agent_version=(request_data.agent_version or "").strip() or None,
        csr_sha256=request_data.csr_sha256.strip().lower(),
        request_fingerprint=fingerprint,
        issuance_id=str(uuid4()),
    )
    session.add(enrollment)
    session.flush()

    token.reserved_at = current_time
    token.reserved_enrollment_id = enrollment.id
    session.flush()

    return ReservationResult(
        token=token,
        enrollment=enrollment,
        resumed=False,
        consumed=False,
    )
