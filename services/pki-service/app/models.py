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


class CertificateStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class Certificate(Base):
    __tablename__ = "certificates"
    __table_args__ = (
        Index("ix_certificates_tenant_status", "tenant_id", "status"),
        Index("ix_certificates_device_status", "device_id", "status"),
        Index("ix_certificates_expiry", "not_after"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    issuance_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    asset_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(64), nullable=False)
    serial_hex: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    csr_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    subject_cn: Mapped[str] = mapped_column(String(255), nullable=False)
    san_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    certificate_pem: Mapped[str] = mapped_column(Text, nullable=False)
    not_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    status: Mapped[CertificateStatus] = mapped_column(
        SAEnum(
            CertificateStatus,
            name="certificate_status",
            native_enum=False,
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        default=CertificateStatus.ACTIVE,
        nullable=False,
    )
    replaces_certificate_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("certificates.id", ondelete="SET NULL"), index=True, nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)


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
