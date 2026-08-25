from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

from .chain import AuditEntry, append_record
from .config import get_settings
from .database import build_engine, build_session_factory
from .normalize import EventNormalizationError, NormalizedAuditEvent, normalize_event

logger = logging.getLogger("guardian.audit.consumer")


@dataclass(frozen=True)
class IngestResult:
    status: str
    event_id: str | None = None
    record_id: str | None = None


def _entry(normalized: NormalizedAuditEvent) -> AuditEntry:
    return AuditEntry(
        tenant_id=normalized.tenant_id,
        source_event_id=normalized.source_event_id,
        source_type=normalized.source_type,
        source_service=normalized.source_service,
        actor_user_id=normalized.actor_user_id,
        actor_type=normalized.actor_type,
        action=normalized.action,
        resource_type=normalized.resource_type,
        resource_id=normalized.resource_id,
        outcome=normalized.outcome,
        request_id=normalized.request_id,
        occurred_at=normalized.occurred_at,
        metadata=normalized.metadata,
    )


async def ingest_message(session_factory, message: Any) -> IngestResult:
    event_id: str | None = None
    try:
        raw = message.data
        if not isinstance(raw, (bytes, bytearray)):
            raise EventNormalizationError("message payload must be bytes")
        decoded = json.loads(bytes(raw).decode("utf-8"))
        normalized = normalize_event(decoded)
        event_id = normalized.source_event_id

        with session_factory() as session:
            record, created = append_record(session, _entry(normalized))
            session.commit()
            record_id = record.id

        # ACK only after commit (or after duplicate lookup/commit completed).
        await message.ack()
        return IngestResult(
            status="inserted" if created else "duplicate",
            event_id=event_id,
            record_id=record_id,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, EventNormalizationError):
        # Do not log the raw message: it can contain secrets from malformed producers.
        logger.warning("Audit event rejected during safe envelope normalization", extra={"event_id": event_id})
        return IngestResult(status="failed", event_id=event_id)
    except Exception:
        # Intentionally omit exception message/payload from structured context because
        # downstream driver errors can echo values. Operators get a stable failure signal.
        logger.exception("Audit event ingestion failed", extra={"event_id": event_id})
        return IngestResult(status="failed", event_id=event_id)


async def _ensure_stream(js, stream_name: str) -> None:
    from nats.js.errors import NotFoundError

    try:
        await js.stream_info(stream_name)
    except NotFoundError:
        await js.add_stream(name=stream_name, subjects=["guardian.>"])


async def run_consumer() -> None:
    import nats
    from nats.errors import TimeoutError as NatsTimeoutError

    settings = get_settings()
    engine = build_engine(settings.database_url)
    session_factory = build_session_factory(engine)
    connection = None

    try:
        while connection is None:
            try:
                connection = await nats.connect(
                    settings.nats_url,
                    connect_timeout=5,
                    max_reconnect_attempts=-1,
                )
            except Exception:
                logger.exception("Unable to connect Audit consumer to NATS; retrying")
                await asyncio.sleep(5)

        js = connection.jetstream()
        await _ensure_stream(js, settings.nats_stream)
        subscription = await js.pull_subscribe(
            "guardian.>",
            durable=settings.nats_durable,
            stream=settings.nats_stream,
        )

        while True:
            try:
                messages = await subscription.fetch(
                    batch=settings.consumer_batch_size,
                    timeout=5,
                )
            except NatsTimeoutError:
                continue
            except Exception:
                logger.exception("Audit JetStream fetch failed; backing off")
                await asyncio.sleep(2)
                continue

            for message in messages:
                result = await ingest_message(session_factory, message)
                if result.status == "failed":
                    # Unacked messages are deliberately left for JetStream redelivery.
                    await asyncio.sleep(0)
    finally:
        if connection is not None:
            await connection.drain()
        engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_consumer())


if __name__ == "__main__":
    main()
