import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select

from .config import get_settings
from .database import Database
from .models import OutboxEvent

logger = logging.getLogger("guardian.tenant.outbox")


class EventPublisher(Protocol):
    async def publish(self, subject: str, payload: bytes) -> None: ...


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


async def publish_pending_once(
    database: Database,
    publisher: EventPublisher,
    *,
    batch_size: int = 100,
) -> dict[str, int]:
    published = 0
    failed = 0
    attempted_ids: set[str] = set()

    for _ in range(batch_size):
        with database.session_factory() as session:
            statement = select(OutboxEvent).where(OutboxEvent.published_at.is_(None))
            if attempted_ids:
                statement = statement.where(OutboxEvent.id.not_in(attempted_ids))
            event = session.scalar(
                statement
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if event is None:
                break

            attempted_ids.add(event.id)
            event.attempts += 1
            subject = f"guardian.{event.event_type}"
            payload = json.dumps(
                event_envelope(event),
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            try:
                await publisher.publish(subject, payload)
            except Exception as exc:  # publisher/network errors must not lose the outbox row
                event.last_error = str(exc)[:2000]
                session.commit()
                failed += 1
                continue

            event.published_at = datetime.now(UTC)
            event.last_error = None
            session.commit()
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

    async def publish(self, subject: str, payload: bytes) -> None:
        if self._jetstream is None:
            raise RuntimeError("NATS JetStream publisher is not connected")
        envelope = json.loads(payload)
        await self._jetstream.publish(
            subject,
            payload,
            headers={"Nats-Msg-Id": envelope["event_id"]},
        )

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.drain()


async def run_worker() -> None:
    settings = get_settings()
    database = Database(settings.database_url)
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
            result = await publish_pending_once(database, publisher, batch_size=100)
            if result["failed"]:
                logger.warning("Outbox publish failures: %s", result)
            if result["published"] == 0:
                await asyncio.sleep(1)
    finally:
        await publisher.close()
        database.engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
