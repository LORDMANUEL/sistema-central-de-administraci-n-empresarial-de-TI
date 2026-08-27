from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.consumer import ingest_message
from app.models import AuditRecord, Base


class FakeMessage:
    def __init__(self, payload: dict | bytes, on_ack=None) -> None:
        self.data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.acked = False
        self.on_ack = on_ack

    async def ack(self):
        if self.on_ack is not None:
            self.on_ack()
        self.acked = True


def event(event_id="event-1"):
    return {
        "schema_version": 1,
        "event_id": event_id,
        "type": "asset.created",
        "aggregate_type": "asset",
        "aggregate_id": "asset-1",
        "occurred_at": "2026-08-24T12:00:00Z",
        "data": {
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "hostname": "WS-001",
        },
    }


def factory():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.mark.asyncio
async def test_message_is_acked_only_after_record_commit():
    engine, session_factory = factory()

    def assert_committed():
        with session_factory() as session:
            assert session.query(AuditRecord).count() == 1

    message = FakeMessage(event(), on_ack=assert_committed)
    result = await ingest_message(session_factory, message)
    assert result.status == "inserted"
    assert result.event_id == "event-1"
    assert message.acked is True
    engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_redelivery_is_acked_without_new_chain_link():
    engine, session_factory = factory()
    first = FakeMessage(event("event-1"))
    second = FakeMessage(event("event-1"))
    first_result = await ingest_message(session_factory, first)
    second_result = await ingest_message(session_factory, second)
    with session_factory() as session:
        assert session.query(AuditRecord).count() == 1
    assert first_result.status == "inserted"
    assert second_result.status == "duplicate"
    assert first.acked is True and second.acked is True
    engine.dispose()


@pytest.mark.asyncio
async def test_invalid_json_or_envelope_is_not_acked_as_success():
    engine, session_factory = factory()
    invalid_json = FakeMessage(b"not-json")
    invalid_envelope = FakeMessage({"schema_version": 1, "event_id": "event-1"})
    one = await ingest_message(session_factory, invalid_json)
    two = await ingest_message(session_factory, invalid_envelope)
    assert one.status == "failed"
    assert two.status == "failed"
    assert invalid_json.acked is False
    assert invalid_envelope.acked is False
    engine.dispose()


@pytest.mark.asyncio
async def test_database_failure_does_not_ack_message():
    class BrokenFactory:
        def __call__(self):
            raise RuntimeError("database unavailable")

    message = FakeMessage(event())
    result = await ingest_message(BrokenFactory(), message)
    assert result.status == "failed"
    assert message.acked is False
