from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TelemetryBatchRecord(Base):
    __tablename__ = "telemetry_batches"
    __table_args__ = (
        UniqueConstraint("device_id", "batch_id", name="uq_telemetry_device_batch"),
    )

    batch_record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    guardian_asset_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    device_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    batch_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    semantic_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_samples: Mapped[int] = mapped_column(Integer, nullable=False)


class TelemetrySample(Base):
    __tablename__ = "telemetry_samples"

    sample_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    batch_record_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("telemetry_batches.batch_record_id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    value: Mapped[int | float] = mapped_column(JSON, nullable=False)
    labels: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
