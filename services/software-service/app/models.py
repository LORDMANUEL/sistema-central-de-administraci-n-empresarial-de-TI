from datetime import UTC,datetime
from uuid import UUID,uuid4
from sqlalchemy import DateTime,JSON,String,UniqueConstraint,Uuid
from sqlalchemy.orm import DeclarativeBase,Mapped,mapped_column
class Base(DeclarativeBase): pass
class SoftwareSnapshot(Base):
    __tablename__="software_snapshots";__table_args__=(UniqueConstraint("device_id","snapshot_id",name="uq_software_device_snapshot"),)
    record_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4)
    tenant_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),nullable=False,index=True)
    guardian_asset_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),nullable=False,index=True)
    device_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),nullable=False,index=True)
    snapshot_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),nullable=False)
    collected_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    received_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(UTC),nullable=False)
    packages:Mapped[list]=mapped_column(JSON,nullable=False)
