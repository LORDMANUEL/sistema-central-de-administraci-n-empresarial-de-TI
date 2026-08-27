import asyncio
import json
from datetime import UTC, datetime

import nats
from nats.js.errors import NotFoundError
from sqlalchemy import select

from .config import get_settings
from .database import build_engine, build_session_factory
from .models import OutboxEvent


def event_envelope(event: OutboxEvent) -> dict:
    """Build the canonical event envelope for command domain delivery."""
    return {
        "schema_version": 1,
        "event_id": str(event.event_id),
        "type": event.subject.removeprefix("guardian."),
        "aggregate_type": "command",
        "aggregate_id": event.aggregate_id,
        "occurred_at": event.created_at.isoformat(),
        "data": event.payload,
    }


async def main():
    settings = get_settings()
    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)
    nc = await nats.connect(
        settings.nats_url,
        connect_timeout=3,
        max_reconnect_attempts=-1,
    )
    js = nc.jetstream()
    try:
        try:
            await js.stream_info(settings.nats_stream)
        except NotFoundError:
            await js.add_stream(name=settings.nats_stream, subjects=["guardian.>"])
        try:
            await js.stream_info(settings.wake_stream)
        except NotFoundError:
            await js.add_stream(
                name=settings.wake_stream,
                subjects=["device.command.available.>"],
            )

        while True:
            with factory() as session:
                rows = session.execute(
                    select(OutboxEvent)
                    .where(OutboxEvent.published_at.is_(None))
                    .order_by(OutboxEvent.created_at)
                    .limit(100)
                ).scalars().all()
                for row in rows:
                    try:
                        await js.publish(
                            row.subject,
                            json.dumps(
                                event_envelope(row),
                                separators=(",", ":"),
                                sort_keys=True,
                            ).encode(),
                            headers={"Nats-Msg-Id": str(row.event_id)},
                        )
                        row.published_at = datetime.now(UTC)
                        row.last_error = None
                    except Exception as exc:
                        row.attempts += 1
                        row.last_error = str(exc)[:512]
                session.commit()
            await asyncio.sleep(1 if rows else 2)
    finally:
        await nc.drain()
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
