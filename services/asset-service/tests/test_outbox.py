import asyncio
import json

from app.database import build_engine, build_session_factory
from app.models import Base, OutboxEvent
from app.outbox_worker import event_envelope, publish_pending_once


class RecordingPublisher:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls: list[tuple[str, bytes]] = []

    async def publish(self, subject: str, payload: bytes) -> None:
        self.calls.append((subject, payload))
        if self.fail:
            raise RuntimeError("nats unavailable")


def _database(tmp_path):
    engine = build_engine(f"sqlite+pysqlite:///{tmp_path / 'outbox.db'}")
    Base.metadata.create_all(engine)
    return engine, build_session_factory(engine)


def _seed(factory, count: int = 1):
    with factory() as session:
        for index in range(count):
            session.add(
                OutboxEvent(
                    event_type="asset.created",
                    aggregate_type="asset",
                    aggregate_id=f"asset-{index}",
                    payload={"tenant_id": "tenant-1", "index": index},
                )
            )
        session.commit()


def test_event_envelope_is_versioned_and_stable(tmp_path):
    _, factory = _database(tmp_path)
    _seed(factory)
    with factory() as session:
        event = session.query(OutboxEvent).one()
        envelope = event_envelope(event)
        assert envelope["schema_version"] == 1
        assert envelope["event_id"] == event.event_id
        assert envelope["type"] == "asset.created"
        assert envelope["aggregate_id"] == "asset-0"
        assert envelope["data"]["tenant_id"] == "tenant-1"


def test_publish_pending_marks_event_only_after_ack(tmp_path):
    _, factory = _database(tmp_path)
    _seed(factory)
    publisher = RecordingPublisher()

    result = asyncio.run(publish_pending_once(factory, publisher, batch_size=10))

    assert result == {"published": 1, "failed": 0}
    assert len(publisher.calls) == 1
    subject, raw = publisher.calls[0]
    assert subject == "guardian.asset.created"
    assert json.loads(raw)["type"] == "asset.created"
    with factory() as session:
        event = session.query(OutboxEvent).one()
        assert event.published_at is not None
        assert event.attempts == 1
        assert event.last_error is None


def test_failed_event_is_retained_and_attempted_once_per_poll(tmp_path):
    _, factory = _database(tmp_path)
    _seed(factory)
    publisher = RecordingPublisher(fail=True)

    result = asyncio.run(publish_pending_once(factory, publisher, batch_size=100))

    assert result == {"published": 0, "failed": 1}
    assert len(publisher.calls) == 1
    with factory() as session:
        event = session.query(OutboxEvent).one()
        assert event.published_at is None
        assert event.attempts == 1
        assert event.last_error == "nats unavailable"


def test_batch_attempts_each_pending_event_at_most_once(tmp_path):
    _, factory = _database(tmp_path)
    _seed(factory, count=3)
    publisher = RecordingPublisher(fail=True)

    result = asyncio.run(publish_pending_once(factory, publisher, batch_size=100))

    assert result == {"published": 0, "failed": 3}
    assert len(publisher.calls) == 3
    with factory() as session:
        events = session.query(OutboxEvent).all()
        assert all(event.attempts == 1 for event in events)
        assert all(event.published_at is None for event in events)
