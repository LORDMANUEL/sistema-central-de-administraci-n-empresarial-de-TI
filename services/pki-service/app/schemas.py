from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IssueCertificateRequest(BaseModel):
    issuance_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    asset_id: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=1, max_length=128)
    platform: str = Field(min_length=1, max_length=64)
    subject_cn: str = Field(min_length=1, max_length=255)
    csr_pem: str = Field(min_length=1, max_length=32768)


class RotateCertificateRequest(IssueCertificateRequest):
    certificate_id: str = Field(min_length=1, max_length=128)


class RevokeCertificateRequest(BaseModel):
    reason: str = Field(default="unspecified", pattern="^(unspecified|key_compromise|affiliation_changed|superseded|cessation_of_operation|privilege_withdrawn)$")


class CertificateResponse(BaseModel):
    certificate_id: str
    issuance_id: str
    tenant_id: str
    asset_id: str
    device_id: str
    platform: str
    serial_hex: str
    fingerprint_sha256: str
    subject_cn: str
    san_uri: str
    certificate_pem: str
    ca_chain_pem: str
    not_before: datetime
    not_after: datetime
    status: str
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
