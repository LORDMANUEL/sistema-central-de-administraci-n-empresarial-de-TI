from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AuditChainHead, AuditRecord, Base


def make_record(*, source_event_id: str, chain_key: str = "platform", sequence: int = 1) -> AuditRecord:
    now = datetime.now(UTC)
    return AuditRecord(
        tenant_id=None,
        sequence=sequence,
        chain_key=chain_key,
        source_event_id=source_event_id,
        source_type="identity.user.created",
        source_service="identity",
        actor_user_id=None,
        actor_type="system",
        action="identity.user.created",
        resource_type="user",
        resource_id="user-1",
        outcome="success",
        request_id="req-1",
        occurred_at=now,
        ingested_at=now,
        metadata_json={},
        prev_hash="0" * 64,
        record_hash="1" * 64,
    )


def test_source_event_id_is_globally_unique():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(make_record(source_event_id="event-1", sequence=1))
        session.commit()
        session.add(make_record(source_event_id="event-1", sequence=2))
        with pytest.raises(IntegrityError):
            session.commit()


def test_chain_sequence_is_unique_per_chain():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(make_record(source_event_id="event-1", sequence=1))
        session.commit()
        session.add(make_record(source_event_id="event-2", sequence=1))
        with pytest.raises(IntegrityError):
            session.commit()


def test_chain_head_tracks_last_sequence_and_hash():
    head = AuditChainHead(
        chain_key="tenant:11111111-1111-1111-1111-111111111111",
        tenant_id="11111111-1111-1111-1111-111111111111",
        last_sequence=7,
        last_hash="a" * 64,
    )
    assert head.chain_key.startswith("tenant:")
    assert head.last_sequence == 7
    assert head.last_hash == "a" * 64
