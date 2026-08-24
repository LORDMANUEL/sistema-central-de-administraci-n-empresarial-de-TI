from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateEnrollmentTokenRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    asset_id: str = Field(min_length=1, max_length=128)
    expires_in_minutes: int = Field(default=60, ge=5, le=1440)


class EnrollmentTokenRead(BaseModel):
    id: str
    tenant_id: str
    asset_id: str
    token_hint: str
    status: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    reserved_at: datetime | None
    consumed_at: datetime | None
    consumed_device_id: str | None


class EnrollmentTokenCreated(EnrollmentTokenRead):
    token: str


class EnrollDeviceRequest(BaseModel):
    token: str = Field(min_length=8, max_length=256)
    platform: str = Field(min_length=1, max_length=64)
    hostname: str = Field(min_length=1, max_length=255)
    agent_version: str | None = Field(default=None, max_length=64)
    csr_pem: str = Field(min_length=1, max_length=32768)


class EnrollmentResult(BaseModel):
    status: str
    device_id: str
    tenant_id: str
    asset_id: str
    certificate_id: str
    certificate_serial_hex: str
    certificate_fingerprint_sha256: str
    certificate_pem: str
    ca_chain_pem: str
    not_before: datetime
    not_after: datetime
