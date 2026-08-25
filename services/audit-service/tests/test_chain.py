from datetime import UTC, datetime

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.chain import AuditEntry, append_record, canonical_record_bytes, compute_record_hash, verify_chain
from app.models import AuditRecord, Base


def entry(event_id: str, *, tenant_id: str | None = None, resource_id: str = "asset-1") -> AuditEntry:
    return AuditEntry(
        tenant_id=tenant_id,
        source_event_id=event_id,
        source_type="asset.created",
        source_service="asset",
        actor_user_id="user-1",
        actor_type="user",
        action="asset.created",
        resource_type="asset",
        resource_id=resource_id,
        outcome="success",
        request_id="req-1",
        occurred_at=datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
        metadata={"hostname": "WS-001", "platform": "windows"},
    )


def session_for_chain():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def test_canonical_hash_does_not_depend_on_dict_insertion_order():
    left = {"b": 2, "a": 1, "nested": {"y": 2, "x": 1}}
    right = {"nested": {"x": 1, "y": 2}, "a": 1, "b": 2}
    assert canonical_record_bytes(left) == canonical_record_bytes(right)
    assert compute_record_hash(left) == compute_record_hash(right)


def test_genesis_record_starts_at_sequence_one_with_zero_prev_hash():
    engine, session = session_for_chain()
    try:
        record, created = append_record(session, entry("event-1"))
        session.commit()
        assert created is True
        assert record.sequence == 1
        assert record.chain_key == "platform"
        assert record.prev_hash == "0" * 64
        assert len(record.record_hash) == 64
    finally:
        session.close()
        engine.dispose()


def test_second_record_references_first_hash_in_tenant_chain():
    tenant_id = "11111111-1111-1111-1111-111111111111"
    engine, session = session_for_chain()
    try:
        first, _ = append_record(session, entry("event-1", tenant_id=tenant_id))
        session.commit()
        second, _ = append_record(session, entry("event-2", tenant_id=tenant_id, resource_id="asset-2"))
        session.commit()
        assert first.sequence == 1
        assert second.sequence == 2
        assert second.prev_hash == first.record_hash
        assert second.chain_key == f"tenant:{tenant_id}"
    finally:
        session.close()
        engine.dispose()


def test_duplicate_source_event_returns_existing_record_without_new_chain_link():
    engine, session = session_for_chain()
    try:
        first, created_one = append_record(session, entry("event-1"))
        session.commit()
        duplicate, created_two = append_record(session, entry("event-1"))
        session.commit()
        count = session.query(AuditRecord).count()
        assert created_one is True
        assert created_two is False
        assert duplicate.id == first.id
        assert count == 1
    finally:
        session.close()
        engine.dispose()


def test_verify_chain_reports_first_tampered_sequence():
    tenant_id = "22222222-2222-2222-2222-222222222222"
    engine, session = session_for_chain()
    try:
        first, _ = append_record(session, entry("event-1", tenant_id=tenant_id))
        session.commit()
        append_record(session, entry("event-2", tenant_id=tenant_id, resource_id="asset-2"))
        session.commit()
        valid = verify_chain(session, f"tenant:{tenant_id}")
        assert valid.valid is True
        assert valid.record_count == 2

        session.execute(
            text("UPDATE audit_records SET resource_id='tampered' WHERE id=:id"),
            {"id": first.id},
        )
        session.commit()
        invalid = verify_chain(session, f"tenant:{tenant_id}")
        assert invalid.valid is False
        assert invalid.first_invalid_sequence == 1
        assert invalid.first_invalid_record_id == first.id
    finally:
        session.close()
        engine.dispose()
