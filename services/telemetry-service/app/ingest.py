from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .metrics_schema import NormalizedSample, validate_sample
from .models import TelemetryBatchRecord, TelemetrySample
from .principal import DevicePrincipal
from .schemas import TelemetryBatchInput


class TelemetryBatchConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BatchAck:
    batch_record_id: UUID
    accepted_samples: int
    duplicate: bool


def _iso(value: datetime) -> str:
    return value.isoformat()


def _normalize_batch(batch: TelemetryBatchInput) -> list[NormalizedSample]:
    return [validate_sample(sample.metric, sample.value, sample.labels) for sample in batch.samples]


def _semantic_digest(batch: TelemetryBatchInput, normalized: list[NormalizedSample]) -> str:
    canonical = {
        "sent_at": _iso(batch.sent_at),
        "samples": [
            {
                "metric": item.metric,
                "value": item.value,
                "labels": dict(sorted(item.labels.items())),
                "observed_at": _iso(source.observed_at),
            }
            for source, item in zip(batch.samples, normalized, strict=True)
        ],
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return sha256(payload).hexdigest()


def ingest_batch(
    session: Session,
    principal: DevicePrincipal,
    batch: TelemetryBatchInput,
    now: datetime,
) -> BatchAck:
    normalized = _normalize_batch(batch)
    digest = _semantic_digest(batch, normalized)

    existing = session.execute(
        select(TelemetryBatchRecord).where(
            TelemetryBatchRecord.device_id == principal.device_id,
            TelemetryBatchRecord.batch_id == batch.batch_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        if existing.semantic_digest != digest:
            raise TelemetryBatchConflict("batch_id was already used for a different telemetry payload")
        return BatchAck(
            batch_record_id=existing.batch_record_id,
            accepted_samples=existing.accepted_samples,
            duplicate=True,
        )

    record = TelemetryBatchRecord(
        tenant_id=principal.tenant_id,
        guardian_asset_id=principal.guardian_asset_id,
        device_id=principal.device_id,
        batch_id=batch.batch_id,
        semantic_digest=digest,
        sent_at=batch.sent_at,
        received_at=now,
        accepted_samples=len(normalized),
    )
    session.add(record)
    session.flush()

    for source, item in zip(batch.samples, normalized, strict=True):
        session.add(
            TelemetrySample(
                batch_record_id=record.batch_record_id,
                metric=item.metric,
                value=item.value,
                labels=item.labels,
                observed_at=source.observed_at,
            )
        )

    session.flush()
    return BatchAck(
        batch_record_id=record.batch_record_id,
        accepted_samples=record.accepted_samples,
        duplicate=False,
    )
