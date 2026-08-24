from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select

from .config import get_settings
from .database import build_engine, build_session_factory
from .metrics import OUTBOX_FAILED, OUTBOX_PUBLISHED
from .models import OutboxEvent

logger = logging.getLogger("guardian.pki.outbox")


class EventPublisher(Protocol):
    async def publish(self, subject: str, payload: bytes, event_id: str) -> None: ...


def event_envelope(event: OutboxEvent) -> dict:
    return {
        "schema_version": 1,
        "event_id": event.event_id,
        "type": event.event_type,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": event.aggregate_id,
        "occurred_at": event.created_at.isoformat(),
        "data": event.payload,
    }


async def publish_pending_once(session_factory, publisher: EventPublisher, *, batch_size: int = 100) -> dict[str, int]:
    published = 0
    failed = 0
    attempted_ids: set[str] = set()
    for _ in range(batch_size):
        with session_factory() as session:
            statement = select(OutboxEvent).where(OutboxEvent.published_at.is_(None))
            if attempted_ids:
                statement = statement.where(OutboxEvent.event_id.not_in(attempted_ids))
            event = session.scalar(
                statement.order_by(OutboxEvent.created_at, OutboxEvent.event_id).limit(1).with_for_update(skip_locked=True)
            )
            if event is None:
                break
            attempted_ids.add(event.event_id)
            event.attempts += 1
            subject = f"guardian.{event.event_type}"
            payload = json.dumps(event_envelope(event), separators=(",", ":"), sort_keys=True).encode("utf-8")
            try:
                await publisher.publish(subject, payload, event.event_id)
            except Exception as exc:
                event.last_error = str(exc)[:2000]
                session.commit()
                OUTBOX_FAILED.inc()
                failed += 1
                continue
            event.published_at = datetime.now(UTC)
            event.last_error = None
            session.commit()
            OUTBOX_PUBLISHED.inc()
            published += 1
    return {"published": published, "failed": failed}


class NatsJetStreamPublisher:
    def __init__(self, url: str, stream: str) -> None:
        self.url = url
        self.stream = stream
        self._connection = None
        self._jetstream = None

    async def connect(self) -> None:
        import nats
        from nats.js.errors import NotFoundError

        self._connection = await nats.connect(self.url, connect_timeout=5, max_reconnect_attempts=-1)
        self._jetstream = self._connection.jetstream()
        try:
            await self._jetstream.stream_info(self.stream)
        except NotFoundError:
            await self._jetstream.add_stream(name=self.stream, subjects=["guardian.>"])

    async def publish(self, subject: str, payload: bytes, event_id: str) -> None:
        if self._jetstream is None:
            raise RuntimeError("NATS JetStream publisher is not connected")
        await self._jetstream.publish(subject, payload, headers={"Nats-Msg-Id": event_id})

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.drain()
            self._connection = None
            self._jetstream = None


async def run_worker() -> None:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    publisher = NatsJetStreamPublisher(settings.nats_url, settings.nats_stream)
    try:
        while True:
            try:
                await publisher.connect()
                break
            except Exception:
                logger.exception("Unable to connect to NATS; retrying")
                await asyncio.sleep(5)
        while True:
            result = await publish_pending_once(session_factory, publisher, batch_size=100)
            if result["failed"]:
                logger.warning("PKI outbox publish failures: %s", result)
            if result["published"] == 0:
                await asyncio.sleep(1)
    finally:
        await publisher.close()
        engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
