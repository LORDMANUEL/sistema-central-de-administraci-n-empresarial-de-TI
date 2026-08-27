from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DeviceSession(Base):
    __tablename__ = "device_sessions"

    device_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    guardian_asset_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    certificate_serial: Mapped[str] = mapped_column(String(128), nullable=False)
    session_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="online")
    agent_version: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(128), nullable=False)
    platform_version: Mapped[str] = mapped_column(String(128), nullable=False)
    current_capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    capability_version: Mapped[int] = mapped_column(Integer, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DeviceCapabilitySnapshot(Base):
    __tablename__ = "device_capability_snapshots"

    snapshot_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    device_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("device_sessions.device_id", ondelete="CASCADE"), nullable=False, index=True
    )
    capability_version: Mapped[int] = mapped_column(Integer, nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
