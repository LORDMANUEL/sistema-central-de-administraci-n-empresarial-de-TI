from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ingest import TelemetryBatchConflict, ingest_batch
from app.models import Base, TelemetryBatchRecord, TelemetrySample
from app.principal import DevicePrincipal
from app.schemas import TelemetryBatchInput, TelemetrySampleInput


def make_batch(*, batch_id=None, cpu: float = 25.0) -> TelemetryBatchInput:
    observed_at = datetime.now(UTC)
    return TelemetryBatchInput(
        batch_id=batch_id or uuid4(),
        sent_at=observed_at,
        samples=[
            TelemetrySampleInput(
                metric="cpu.utilization_pct",
                value=cpu,
                labels={},
                observed_at=observed_at,
            ),
            TelemetrySampleInput(
                metric="disk.free_bytes",
                value=1024,
                labels={"volume": "C:"},
                observed_at=observed_at,
            ),
        ],
    )


def make_principal(*, device_id=None) -> DevicePrincipal:
    return DevicePrincipal(
        tenant_id=uuid4(),
        guardian_asset_id=uuid4(),
        device_id=device_id or uuid4(),
        certificate_serial="01AB",
    )


def test_identical_duplicate_batch_returns_same_ack_without_duplicate_samples():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    principal = make_principal()
    batch = make_batch()
    now = datetime.now(UTC)
    with Session(engine) as session:
        first = ingest_batch(session, principal, batch, now)
        second = ingest_batch(session, principal, batch, now)
        assert second.batch_record_id == first.batch_record_id
        assert second.duplicate is True
        assert session.execute(select(TelemetryBatchRecord)).scalars().all().__len__() == 1
        assert session.execute(select(TelemetrySample)).scalars().all().__len__() == 2
    engine.dispose()


def test_same_batch_id_with_different_payload_conflicts():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    principal = make_principal()
    batch_id = uuid4()
    now = datetime.now(UTC)
    with Session(engine) as session:
        ingest_batch(session, principal, make_batch(batch_id=batch_id, cpu=25.0), now)
        with pytest.raises(TelemetryBatchConflict):
            ingest_batch(session, principal, make_batch(batch_id=batch_id, cpu=26.0), now)
    engine.dispose()


def test_same_batch_id_isolated_per_device():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    batch_id = uuid4()
    now = datetime.now(UTC)
    with Session(engine) as session:
        first = ingest_batch(session, make_principal(), make_batch(batch_id=batch_id), now)
        second = ingest_batch(session, make_principal(), make_batch(batch_id=batch_id), now)
        assert first.batch_record_id != second.batch_record_id
        assert session.execute(select(TelemetryBatchRecord)).scalars().all().__len__() == 2
    engine.dispose()
