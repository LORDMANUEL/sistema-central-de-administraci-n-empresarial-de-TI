from __future__ import annotations

from datetime import UTC, datetime

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .api import _load_signer_and_chain, _public_key_der, _response, _same_issuance
from .certificates import issue_device_certificate, parse_and_validate_csr
from .database import get_db
from .errors import GuardianError
from .models import Certificate, CertificateStatus, OutboxEvent
from .schemas import CertificateResponse, RotateCertificateRequest

router = APIRouter(prefix="/api/v1")
_bearer = HTTPBearer(auto_error=False)


def _require_rotation_grant(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    payload: RotateCertificateRequest,
    csr_sha256: str,
) -> None:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise GuardianError(401, "pki.enrollment_grant_required", "Enrollment rotation grant is required")
    grant = request.app.state.grant_verifier.verify(
        credentials.credentials,
        expected_type="certificate_rotate",
    )
    if (
        grant.tenant_id != payload.tenant_id
        or grant.asset_id != payload.asset_id
        or grant.device_id != payload.device_id
        or grant.issuance_id != payload.issuance_id
        or grant.csr_sha256 != csr_sha256
    ):
        raise GuardianError(403, "pki.grant_binding_mismatch", "Enrollment grant does not match rotation request")


def _same_rotation(
    existing: Certificate,
    old: Certificate,
    payload: RotateCertificateRequest,
    csr_sha256: str,
) -> bool:
    return existing.replaces_certificate_id == old.id and _same_issuance(existing, payload, csr_sha256)


@router.post("/certificates/rotate", response_model=CertificateResponse, status_code=status.HTTP_201_CREATED)
def rotate_certificate(
    payload: RotateCertificateRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CertificateResponse:
    validated_csr = parse_and_validate_csr(payload.csr_pem)
    _require_rotation_grant(request, credentials, payload, validated_csr.csr_sha256)

    old = session.get(Certificate, payload.certificate_id)
    if old is None:
        raise GuardianError(404, "pki.certificate_not_found", "Certificate not found")
    if (
        old.tenant_id != payload.tenant_id
        or old.asset_id != payload.asset_id
        or old.device_id != payload.device_id
        or old.platform != payload.platform
    ):
        raise GuardianError(409, "pki.rotation_identity_mismatch", "Rotation identity does not match existing certificate")

    signer_cert, signer_key, ca_chain_pem = _load_signer_and_chain(request)
    existing = session.scalar(select(Certificate).where(Certificate.issuance_id == payload.issuance_id))
    if existing is not None:
        if not _same_rotation(existing, old, payload, validated_csr.csr_sha256):
            raise GuardianError(409, "pki.issuance_conflict", "Issuance ID is already bound to different certificate data")
        response.status_code = status.HTTP_200_OK
        return _response(existing, ca_chain_pem)

    if old.status == CertificateStatus.REVOKED:
        raise GuardianError(409, "pki.certificate_revoked", "Certificate is already revoked")

    old_certificate = x509.load_pem_x509_certificate(old.certificate_pem.encode("ascii"))
    if _public_key_der(old_certificate.public_key()) == _public_key_der(validated_csr.csr.public_key()):
        raise GuardianError(409, "pki.rotation_key_reuse", "Certificate rotation requires a new device key")

    issued = issue_device_certificate(
        validated_csr,
        signer_cert=signer_cert,
        signer_key=signer_key,
        tenant_id=payload.tenant_id,
        asset_id=payload.asset_id,
        device_id=payload.device_id,
        platform=payload.platform,
        subject_cn=payload.subject_cn,
        lifetime_days=request.app.state.settings.certificate_lifetime_days,
        clock_skew_seconds=request.app.state.settings.clock_skew_seconds,
    )
    replacement = Certificate(
        issuance_id=payload.issuance_id,
        tenant_id=payload.tenant_id,
        asset_id=payload.asset_id,
        device_id=payload.device_id,
        platform=payload.platform,
        serial_hex=issued.serial_hex,
        csr_sha256=issued.csr_sha256,
        fingerprint_sha256=issued.fingerprint_sha256,
        subject_cn=payload.subject_cn.strip(),
        san_uri=issued.san_uri,
        certificate_pem=issued.certificate_pem,
        not_before=issued.not_before,
        not_after=issued.not_after,
        status=CertificateStatus.ACTIVE,
        replaces_certificate_id=old.id,
    )
    session.add(replacement)
    try:
        session.flush()
        old.status = CertificateStatus.REVOKED
        old.revoked_at = datetime.now(UTC)
        old.revocation_reason = "superseded"
        session.add(
            OutboxEvent(
                event_type="pki.certificate.rotated",
                aggregate_type="certificate",
                aggregate_id=replacement.id,
                payload={
                    "old_certificate_id": old.id,
                    "new_certificate_id": replacement.id,
                    "issuance_id": replacement.issuance_id,
                    "tenant_id": replacement.tenant_id,
                    "asset_id": replacement.asset_id,
                    "device_id": replacement.device_id,
                    "serial_hex": replacement.serial_hex,
                    "old_serial_hex": old.serial_hex,
                },
            )
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        concurrent = session.scalar(select(Certificate).where(Certificate.issuance_id == payload.issuance_id))
        old = session.get(Certificate, payload.certificate_id)
        if concurrent is not None and old is not None and _same_rotation(concurrent, old, payload, validated_csr.csr_sha256):
            response.status_code = status.HTTP_200_OK
            return _response(concurrent, ca_chain_pem)
        raise GuardianError(409, "pki.issuance_conflict", "Rotation issuance conflicts with existing certificate data") from exc

    session.refresh(replacement)
    return _response(replacement, ca_chain_pem)
