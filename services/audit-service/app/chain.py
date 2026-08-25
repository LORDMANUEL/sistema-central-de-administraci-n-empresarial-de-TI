from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import AuditChainHead, AuditRecord

ZERO_HASH = "0" * 64


@dataclass(frozen=True)
class AuditEntry:
    tenant_id: str | None
    source_event_id: str
    source_type: str
    source_service: str
    actor_user_id: str | None
    actor_type: str
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    request_id: str | None
    occurred_at: datetime
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    record_count: int
    last_sequence: int
    last_hash: str
    first_invalid_sequence: int | None = None
    first_invalid_record_id: str | None = None


def _canonical_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def canonical_record_bytes(fields: dict[str, Any]) -> bytes:
    normalized = _canonical_value(fields)
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def compute_record_hash(fields: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_record_bytes(fields)).hexdigest()


def _chain_key(tenant_id: str | None) -> str:
    return f"tenant:{tenant_id}" if tenant_id else "platform"


def _lock_key(session: Session, value: str) -> None:
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:value, 0))"),
            {"value": value},
        )


def _hash_fields(record: AuditRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "sequence": record.sequence,
        "chain_key": record.chain_key,
        "source_event_id": record.source_event_id,
        "source_type": record.source_type,
        "source_service": record.source_service,
        "actor_user_id": record.actor_user_id,
        "actor_type": record.actor_type,
        "action": record.action,
        "resource_type": record.resource_type,
        "resource_id": record.resource_id,
        "outcome": record.outcome,
        "request_id": record.request_id,
        "occurred_at": record.occurred_at,
        "ingested_at": record.ingested_at,
        "metadata": record.metadata_json,
        "prev_hash": record.prev_hash,
    }


def append_record(session: Session, entry: AuditEntry) -> tuple[AuditRecord, bool]:
    chain_key = _chain_key(entry.tenant_id)

    # Serialize concurrent retries for the same immutable source event first,
    # then serialize appends to one chain. The order is always event -> chain.
    _lock_key(session, f"audit-event:{entry.source_event_id}")
    existing = session.scalar(
        select(AuditRecord).where(AuditRecord.source_event_id == entry.source_event_id)
    )
    if existing is not None:
        return existing, False

    _lock_key(session, f"audit-chain:{chain_key}")
    head = session.scalar(
        select(AuditChainHead)
        .where(AuditChainHead.chain_key == chain_key)
        .with_for_update()
    )
    if head is None:
        head = AuditChainHead(
            chain_key=chain_key,
            tenant_id=entry.tenant_id,
            last_sequence=0,
            last_hash=ZERO_HASH,
        )
        session.add(head)
        session.flush()

    now = datetime.now(UTC)
    record = AuditRecord(
        id=str(uuid4()),
        tenant_id=entry.tenant_id,
        sequence=head.last_sequence + 1,
        chain_key=chain_key,
        source_event_id=entry.source_event_id,
        source_type=entry.source_type,
        source_service=entry.source_service,
        actor_user_id=entry.actor_user_id,
        actor_type=entry.actor_type,
        action=entry.action,
        resource_type=entry.resource_type,
        resource_id=entry.resource_id,
        outcome=entry.outcome,
        request_id=entry.request_id,
        occurred_at=entry.occurred_at,
        ingested_at=now,
        metadata_json=entry.metadata,
        prev_hash=head.last_hash,
        record_hash=ZERO_HASH,
    )
    record.record_hash = compute_record_hash(_hash_fields(record))
    session.add(record)
    session.flush()

    head.last_sequence = record.sequence
    head.last_hash = record.record_hash
    head.updated_at = now
    session.flush()
    return record, True


def verify_chain(session: Session, chain_key: str) -> ChainVerification:
    records = list(
        session.scalars(
            select(AuditRecord)
            .where(AuditRecord.chain_key == chain_key)
            .order_by(AuditRecord.sequence.asc())
        )
    )

    expected_prev = ZERO_HASH
    expected_sequence = 1
    last_hash = ZERO_HASH

    for record in records:
        recomputed = compute_record_hash(_hash_fields(record))
        if (
            record.sequence != expected_sequence
            or record.prev_hash != expected_prev
            or record.record_hash != recomputed
        ):
            return ChainVerification(
                valid=False,
                record_count=len(records),
                last_sequence=record.sequence,
                last_hash=record.record_hash,
                first_invalid_sequence=record.sequence,
                first_invalid_record_id=record.id,
            )
        expected_prev = record.record_hash
        last_hash = record.record_hash
        expected_sequence += 1

    last_sequence = len(records)
    head = session.get(AuditChainHead, chain_key)
    if head is not None and (
        head.last_sequence != last_sequence or head.last_hash != last_hash
    ):
        return ChainVerification(
            valid=False,
            record_count=len(records),
            last_sequence=last_sequence,
            last_hash=last_hash,
            first_invalid_sequence=last_sequence if last_sequence else 0,
            first_invalid_record_id=records[-1].id if records else None,
        )

    return ChainVerification(
        valid=True,
        record_count=len(records),
        last_sequence=last_sequence,
        last_hash=last_hash,
    )
