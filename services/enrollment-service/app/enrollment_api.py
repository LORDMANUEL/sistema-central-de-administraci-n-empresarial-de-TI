from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .csr import validate_csr
from .database import get_db
from .errors import GuardianError
from .models import DeviceEnrollment, EnrollmentStatus, EnrollmentToken, OutboxEvent
from .reservation import EnrollmentRequestData, reserve_or_resume
from .schemas import EnrollDeviceRequest, EnrollmentResult

router = APIRouter(prefix="/api/v1")


def _result(enrollment: DeviceEnrollment) -> EnrollmentResult:
    required = (
        enrollment.certificate_id,
        enrollment.certificate_serial_hex,
        enrollment.certificate_fingerprint_sha256,
        enrollment.certificate_pem,
        enrollment.ca_chain_pem,
        enrollment.certificate_not_before,
        enrollment.certificate_not_after,
    )
    if enrollment.status != EnrollmentStatus.ENROLLED or not all(required):
        raise GuardianError(409, "enrollment.not_complete", "Device enrollment is not complete")
    return EnrollmentResult(
        status="enrolled",
        device_id=enrollment.device_id,
        tenant_id=enrollment.tenant_id,
        asset_id=enrollment.asset_id,
        certificate_id=enrollment.certificate_id,
        certificate_serial_hex=enrollment.certificate_serial_hex,
        certificate_fingerprint_sha256=enrollment.certificate_fingerprint_sha256,
        certificate_pem=enrollment.certificate_pem,
        ca_chain_pem=enrollment.ca_chain_pem,
        not_before=enrollment.certificate_not_before,
        not_after=enrollment.certificate_not_after,
    )


def _persist_pki_failure(
    session: Session,
    *,
    enrollment_id: str,
    token_id: str,
    error: GuardianError,
) -> None:
    enrollment = session.scalar(
        select(DeviceEnrollment)
        .where(DeviceEnrollment.id == enrollment_id)
        .with_for_update()
    )
    token = session.scalar(
        select(EnrollmentToken)
        .where(EnrollmentToken.id == token_id)
        .with_for_update()
    )
    if enrollment is None or token is None:
        session.rollback()
        return

    enrollment.failure_code = error.code
    enrollment.failure_message = "PKI certificate issuance did not complete"

    if error.code == "enrollment.pki_rejected" and enrollment.certificate_id is None:
        enrollment.status = EnrollmentStatus.FAILED
        token.reserved_at = None
        token.reserved_enrollment_id = None
        session.add(
            OutboxEvent(
                event_type="device.enrollment.failed",
                aggregate_type="device",
                aggregate_id=enrollment.device_id,
                payload={
                    "device_id": enrollment.device_id,
                    "tenant_id": enrollment.tenant_id,
                    "asset_id": enrollment.asset_id,
                    "platform": enrollment.platform,
                    "hostname": enrollment.hostname,
                    "failure_code": error.code,
                    "failed_at": datetime.now(UTC).isoformat(),
                },
            )
        )
    else:
        # Network/5xx uncertainty and issuance conflicts keep the reservation
        # and stable IDs. Retrying with the same request cannot roll identity.
        enrollment.status = EnrollmentStatus.PENDING

    session.commit()


@router.post("/enrollments", response_model=EnrollmentResult, status_code=status.HTTP_201_CREATED)
def enroll_device(
    payload: EnrollDeviceRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> EnrollmentResult:
    validated_csr = validate_csr(payload.csr_pem)
    request_data = EnrollmentRequestData(
        platform=payload.platform,
        hostname=payload.hostname,
        agent_version=payload.agent_version,
        csr_sha256=validated_csr.csr_sha256,
    )

    reservation = reserve_or_resume(session, payload.token, request_data)
    if reservation.consumed:
        response.status_code = status.HTTP_200_OK
        return _result(reservation.enrollment)

    session.commit()
    enrollment_id = reservation.enrollment.id
    token_id = reservation.token.id
    resumed = reservation.resumed

    signer = request.app.state.signer
    if signer is None:
        raise GuardianError(503, "enrollment.signer_unavailable", "Enrollment signing material is unavailable")
    grant = signer.create_issue_grant(
        tenant_id=reservation.enrollment.tenant_id,
        asset_id=reservation.enrollment.asset_id,
        device_id=reservation.enrollment.device_id,
        issuance_id=reservation.enrollment.issuance_id,
        csr_sha256=reservation.enrollment.csr_sha256,
    )

    try:
        certificate = request.app.state.pki_client.issue(
            grant=grant,
            issuance_id=reservation.enrollment.issuance_id,
            tenant_id=reservation.enrollment.tenant_id,
            asset_id=reservation.enrollment.asset_id,
            device_id=reservation.enrollment.device_id,
            platform=reservation.enrollment.platform,
            subject_cn=reservation.enrollment.hostname,
            csr_pem=payload.csr_pem,
        )
    except GuardianError as exc:
        _persist_pki_failure(
            session,
            enrollment_id=enrollment_id,
            token_id=token_id,
            error=exc,
        )
        raise

    enrollment = session.scalar(
        select(DeviceEnrollment)
        .where(DeviceEnrollment.id == enrollment_id)
        .with_for_update()
    )
    token = session.scalar(
        select(EnrollmentToken)
        .where(EnrollmentToken.id == token_id)
        .with_for_update()
    )
    if enrollment is None or token is None:
        raise GuardianError(409, "enrollment.state_inconsistent", "Enrollment state is inconsistent")

    if enrollment.status == EnrollmentStatus.ENROLLED and token.consumed_at is not None:
        session.rollback()
        response.status_code = status.HTTP_200_OK
        return _result(enrollment)

    now = datetime.now(UTC)
    enrollment.status = EnrollmentStatus.ENROLLED
    enrollment.certificate_id = certificate.certificate_id
    enrollment.certificate_serial_hex = certificate.serial_hex
    enrollment.certificate_fingerprint_sha256 = certificate.fingerprint_sha256
    enrollment.certificate_pem = certificate.certificate_pem
    enrollment.ca_chain_pem = certificate.ca_chain_pem
    enrollment.certificate_not_before = certificate.not_before
    enrollment.certificate_not_after = certificate.not_after
    enrollment.failure_code = None
    enrollment.failure_message = None
    enrollment.enrolled_at = now
    token.consumed_at = now
    token.consumed_device_id = enrollment.device_id

    session.add(
        OutboxEvent(
            event_type="device.enrolled",
            aggregate_type="device",
            aggregate_id=enrollment.device_id,
            payload={
                "device_id": enrollment.device_id,
                "tenant_id": enrollment.tenant_id,
                "asset_id": enrollment.asset_id,
                "platform": enrollment.platform,
                "hostname": enrollment.hostname,
                "agent_version": enrollment.agent_version,
                "certificate_id": enrollment.certificate_id,
                "certificate_serial_hex": enrollment.certificate_serial_hex,
                "certificate_fingerprint_sha256": enrollment.certificate_fingerprint_sha256,
                "certificate_not_after": enrollment.certificate_not_after.isoformat(),
                "enrolled_at": now.isoformat(),
            },
        )
    )
    session.commit()
    session.refresh(enrollment)
    if resumed:
        response.status_code = status.HTTP_200_OK
    return _result(enrollment)
