import asyncio
import json

from app.database import Base, build_engine, build_session_factory
from app.models import OutboxEvent
from app.outbox_worker import event_envelope, publish_pending_once


class RecordingPublisher:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls: list[tuple[str, bytes, str]] = []

    async def publish(self, subject: str, payload: bytes, event_id: str) -> None:
        self.calls.append((subject, payload, event_id))
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
                    event_type="device.enrolled",
                    aggregate_type="device",
                    aggregate_id=f"device-{index}",
                    payload={"tenant_id": "tenant-1", "index": index},
                )
            )
        session.commit()


def test_event_envelope_matches_guardian_schema_v1(tmp_path):
    engine, factory = _database(tmp_path)
    try:
        _seed(factory)
        with factory() as session:
            event = session.query(OutboxEvent).one()
            envelope = event_envelope(event)
        assert envelope["schema_version"] == 1
        assert envelope["event_id"] == event.event_id
        assert envelope["type"] == "device.enrolled"
        assert envelope["aggregate_type"] == "device"
        assert envelope["aggregate_id"] == "device-0"
        assert envelope["data"]["tenant_id"] == "tenant-1"
    finally:
        engine.dispose()


def test_publish_marks_event_only_after_ack(tmp_path):
    engine, factory = _database(tmp_path)
    try:
        _seed(factory)
        publisher = RecordingPublisher()
        result = asyncio.run(publish_pending_once(factory, publisher, batch_size=10))
        assert result == {"published": 1, "failed": 0}
        assert len(publisher.calls) == 1
        subject, raw, event_id = publisher.calls[0]
        assert subject == "guardian.device.enrolled"
        assert json.loads(raw)["event_id"] == event_id
        with factory() as session:
            event = session.query(OutboxEvent).one()
            assert event.published_at is not None
            assert event.attempts == 1
            assert event.last_error is None
    finally:
        engine.dispose()


def test_failure_retains_events_and_attempts_each_once_per_poll(tmp_path):
    engine, factory = _database(tmp_path)
    try:
        _seed(factory, count=3)
        publisher = RecordingPublisher(fail=True)
        result = asyncio.run(publish_pending_once(factory, publisher, batch_size=100))
        assert result == {"published": 0, "failed": 3}
        assert len(publisher.calls) == 3
        with factory() as session:
            events = session.query(OutboxEvent).order_by(OutboxEvent.aggregate_id).all()
            assert all(event.published_at is None for event in events)
            assert all(event.attempts == 1 for event in events)
            assert all(event.last_error == "nats unavailable" for event in events)
    finally:
        engine.dispose()
