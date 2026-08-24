from __future__ import annotations

from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .certificates import issue_device_certificate, parse_and_validate_csr
from .database import get_db
from .errors import GuardianError
from .models import Certificate, CertificateStatus, OutboxEvent
from .schemas import CertificateResponse, IssueCertificateRequest

router = APIRouter(prefix="/api/v1")
_bearer = HTTPBearer(auto_error=False)


def _public_key_der(key) -> bytes:
    return key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _load_signer_and_chain(request: Request):
    settings = request.app.state.settings
    root_cert_path = getattr(request.app.state, "root_cert_path", settings.root_cert_path)
    try:
        signer_cert = x509.load_pem_x509_certificate(Path(settings.ca_cert_path).read_bytes())
        signer_key = serialization.load_pem_private_key(Path(settings.ca_key_path).read_bytes(), password=None)
        root_cert = x509.load_pem_x509_certificate(Path(root_cert_path).read_bytes())
        if _public_key_der(signer_cert.public_key()) != _public_key_der(signer_key.public_key()):
            raise ValueError("signer certificate and private key do not match")
        if not signer_cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            raise ValueError("signer certificate is not a CA")
    except Exception as exc:
        raise GuardianError(503, "pki.ca_unavailable", "PKI online signing material is unavailable") from exc

    signer_pem = signer_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    root_pem = root_cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    return signer_cert, signer_key, f"{signer_pem}{root_pem}"


def _same_issuance(existing: Certificate, payload: IssueCertificateRequest, csr_sha256: str) -> bool:
    return (
        existing.issuance_id == payload.issuance_id
        and existing.tenant_id == payload.tenant_id
        and existing.asset_id == payload.asset_id
        and existing.device_id == payload.device_id
        and existing.platform == payload.platform
        and existing.subject_cn == payload.subject_cn.strip()
        and existing.csr_sha256 == csr_sha256
    )


def _response(existing: Certificate, ca_chain_pem: str) -> CertificateResponse:
    return CertificateResponse(
        certificate_id=existing.id,
        issuance_id=existing.issuance_id,
        tenant_id=existing.tenant_id,
        asset_id=existing.asset_id,
        device_id=existing.device_id,
        platform=existing.platform,
        serial_hex=existing.serial_hex,
        fingerprint_sha256=existing.fingerprint_sha256,
        subject_cn=existing.subject_cn,
        san_uri=existing.san_uri,
        certificate_pem=existing.certificate_pem,
        ca_chain_pem=ca_chain_pem,
        not_before=existing.not_before,
        not_after=existing.not_after,
        status=existing.status.value if isinstance(existing.status, CertificateStatus) else str(existing.status),
    )


def _require_issue_grant(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    payload: IssueCertificateRequest,
    csr_sha256: str,
):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise GuardianError(401, "pki.enrollment_grant_required", "Enrollment issuance grant is required")
    grant = request.app.state.grant_verifier.verify(
        credentials.credentials,
        expected_type="certificate_issue",
    )
    if (
        grant.tenant_id != payload.tenant_id
        or grant.asset_id != payload.asset_id
        or grant.device_id != payload.device_id
        or grant.issuance_id != payload.issuance_id
        or grant.csr_sha256 != csr_sha256
    ):
        raise GuardianError(403, "pki.grant_binding_mismatch", "Enrollment grant does not match certificate request")
    return grant


@router.post("/certificates/issue", response_model=CertificateResponse, status_code=status.HTTP_201_CREATED)
def issue_certificate(
    payload: IssueCertificateRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CertificateResponse:
    validated_csr = parse_and_validate_csr(payload.csr_pem)
    _require_issue_grant(request, credentials, payload, validated_csr.csr_sha256)
    signer_cert, signer_key, ca_chain_pem = _load_signer_and_chain(request)

    existing = session.scalar(select(Certificate).where(Certificate.issuance_id == payload.issuance_id))
    if existing is not None:
        if not _same_issuance(existing, payload, validated_csr.csr_sha256):
            raise GuardianError(409, "pki.issuance_conflict", "Issuance ID is already bound to different certificate data")
        response.status_code = status.HTTP_200_OK
        return _response(existing, ca_chain_pem)

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
    certificate = Certificate(
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
    )
    session.add(certificate)
    try:
        session.flush()
        session.add(
            OutboxEvent(
                event_type="pki.certificate.issued",
                aggregate_type="certificate",
                aggregate_id=certificate.id,
                payload={
                    "certificate_id": certificate.id,
                    "issuance_id": certificate.issuance_id,
                    "tenant_id": certificate.tenant_id,
                    "asset_id": certificate.asset_id,
                    "device_id": certificate.device_id,
                    "platform": certificate.platform,
                    "serial_hex": certificate.serial_hex,
                    "fingerprint_sha256": certificate.fingerprint_sha256,
                    "not_after": certificate.not_after.isoformat(),
                },
            )
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        concurrent = session.scalar(select(Certificate).where(Certificate.issuance_id == payload.issuance_id))
        if concurrent is not None and _same_issuance(concurrent, payload, validated_csr.csr_sha256):
            response.status_code = status.HTTP_200_OK
            return _response(concurrent, ca_chain_pem)
        raise GuardianError(409, "pki.issuance_conflict", "Issuance ID conflicts with existing certificate data") from exc

    session.refresh(certificate)
    return _response(certificate, ca_chain_pem)
