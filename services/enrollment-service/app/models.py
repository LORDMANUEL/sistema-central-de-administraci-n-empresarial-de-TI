from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class EnrollmentStatus(str, Enum):
    PENDING = "pending"
    CERTIFICATE_ISSUED = "certificate_issued"
    ENROLLED = "enrolled"
    FAILED = "failed"


class EnrollmentToken(Base):
    __tablename__ = "enrollment_tokens"
    __table_args__ = (
        Index("ix_enrollment_tokens_tenant_expiry", "tenant_id", "expires_at"),
        Index("ix_enrollment_tokens_tenant_consumed", "tenant_id", "consumed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    token_hint: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    asset_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reserved_enrollment_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_device_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class DeviceEnrollment(Base):
    __tablename__ = "device_enrollments"
    __table_args__ = (
        Index("ix_device_enrollments_tenant_status", "tenant_id", "status"),
        Index("ix_device_enrollments_asset_status", "asset_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    token_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("enrollment_tokens.id", ondelete="RESTRICT"), unique=True, index=True, nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    asset_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    csr_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    issuance_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    status: Mapped[EnrollmentStatus] = mapped_column(
        SAEnum(
            EnrollmentStatus,
            name="enrollment_status",
            native_enum=False,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        default=EnrollmentStatus.PENDING,
        nullable=False,
    )
    certificate_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    certificate_serial_hex: Mapped[str | None] = mapped_column(String(64), nullable=True)
    certificate_fingerprint_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    certificate_pem: Mapped[str | None] = mapped_column(Text, nullable=True)
    ca_chain_pem: Mapped[str | None] = mapped_column(Text, nullable=True)
    certificate_not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    certificate_not_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
