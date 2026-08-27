import asyncio
import json
from datetime import UTC, datetime

import nats
from sqlalchemy import select

from .config import get_settings
from .database import build_engine, build_session_factory
from .models import OutboxEvent


async def run_once():
    settings = get_settings()
    engine = build_engine(settings.database_url)
    factory = build_session_factory(engine)
    nc = await nats.connect(settings.nats_url, connect_timeout=3)
    js = nc.jetstream()
    try:
        try:
            await js.add_stream(name=settings.nats_stream, subjects=["device.*"])
        except Exception:
            pass
        with factory() as session:
            rows = session.execute(select(OutboxEvent).where(OutboxEvent.published_at.is_(None)).order_by(OutboxEvent.created_at).limit(100)).scalars().all()
            for row in rows:
                try:
                    await js.publish(row.event_type, json.dumps(row.payload, separators=(",", ":")).encode(), headers={"Nats-Msg-Id": str(row.event_id)})
                    row.published_at = datetime.now(UTC)
                    row.last_error = None
                except Exception as exc:
                    row.attempts += 1
                    row.last_error = str(exc)[:512]
            session.commit()
    finally:
        await nc.drain()
        engine.dispose()


async def main():
    while True:
        try:
            await run_once()
        except Exception:
            pass
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
