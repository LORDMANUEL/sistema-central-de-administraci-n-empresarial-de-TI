from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class AuditChainHead(Base):
    __tablename__ = "audit_chain_heads"

    chain_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="0" * 64)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class AuditRecord(Base):
    __tablename__ = "audit_records"
    __table_args__ = (
        UniqueConstraint("chain_key", "sequence", name="uq_audit_record_chain_sequence"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    chain_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_event_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    source_service: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
