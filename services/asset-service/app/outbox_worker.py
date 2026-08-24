from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import nats
from nats.js.api import StreamConfig
from sqlalchemy import select

from .config import get_settings
from .database import build_engine, build_session_factory
from .models import OutboxEvent


async def run() -> None:
    settings = get_settings()
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    nc = await nats.connect(settings.nats_url)
    js = nc.jetstream()
    try:
        try:
            await js.stream_info(settings.nats_stream)
        except Exception:
            await js.add_stream(StreamConfig(name=settings.nats_stream, subjects=["guardian.>"]))

        while True:
            with session_factory() as session:
                event = session.scalar(
                    select(OutboxEvent)
                    .where(OutboxEvent.published_at.is_(None))
                    .order_by(OutboxEvent.created_at)
                    .limit(1)
                )
                if event is None:
                    await asyncio.sleep(0.5)
                    continue
                subject = f"guardian.{event.event_type}"
                payload = json.dumps(
                    {
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "aggregate_type": event.aggregate_type,
                        "aggregate_id": event.aggregate_id,
                        "payload": event.payload,
                        "created_at": event.created_at.isoformat(),
                    }
                ).encode()
                try:
                    await js.publish(subject, payload, headers={"Nats-Msg-Id": event.event_id})
                except Exception:
                    await asyncio.sleep(1.0)
                    continue
                event.published_at = datetime.now(timezone.utc)
                session.commit()
    finally:
        await nc.drain()


if __name__ == "__main__":
    asyncio.run(run())
