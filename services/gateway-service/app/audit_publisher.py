from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Awaitable, Callable, Protocol
from uuid import uuid4

import httpx

from .errors import GatewayError
from .routes import RoutePolicy


class AuditEventPublisher(Protocol):
    async def publish(self, subject: str, payload: bytes, *, event_id: str) -> None: ...


class NatsJetStreamAuditPublisher:
    """Lazy JetStream publisher used by the northbound Gateway.

    No connection URL or driver exception is logged here. Required audit intent errors
    are converted to a stable secret-safe 503 by execute_with_audit().
    """

    def __init__(self, url: str, stream: str, *, connect_timeout_seconds: float = 3.0) -> None:
        self._url = url
        self._stream = stream
        self._connect_timeout_seconds = connect_timeout_seconds
        self._connection = None
        self._jetstream = None
        self._lock = asyncio.Lock()

    async def _ensure_connected(self):
        if self._connection is not None and not self._connection.is_closed and self._jetstream is not None:
            return self._jetstream

        async with self._lock:
            if self._connection is not None and not self._connection.is_closed and self._jetstream is not None:
                return self._jetstream

            import nats
            from nats.js.errors import NotFoundError

            connection = await nats.connect(
                self._url,
                connect_timeout=self._connect_timeout_seconds,
                max_reconnect_attempts=2,
            )
            jetstream = connection.jetstream()
            try:
                await jetstream.stream_info(self._stream)
            except NotFoundError:
                try:
                    await jetstream.add_stream(name=self._stream, subjects=["guardian.>"])
                except Exception:
                    # A second service may have created the stream concurrently.
                    await jetstream.stream_info(self._stream)

            self._connection = connection
            self._jetstream = jetstream
            return jetstream

    async def publish(self, subject: str, payload: bytes, *, event_id: str) -> None:
        jetstream = await self._ensure_connected()
        await jetstream.publish(
            subject,
            payload,
            headers={"Nats-Msg-Id": event_id},
            timeout=self._connect_timeout_seconds,
        )

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.drain()
        self._connection = None
        self._jetstream = None


@dataclass(frozen=True)
class GatewayAuditContext:
    request_id: str
    route_id: str
    method: str
    actor_user_id: str | None
    tenant_id: str | None
    client_ip: str | None


@dataclass(frozen=True)
class GatewayExecutionResult:
    response: httpx.Response
    completion_audit_failed: bool = False


def _event_payload(
    event_type: str,
    context: GatewayAuditContext,
    *,
    status_code: int | None = None,
    outcome: str,
) -> tuple[str, bytes]:
    event_id = str(uuid4())
    data: dict[str, object] = {
        "actor_type": "user" if context.actor_user_id else "system",
        "action": context.route_id,
        "outcome": outcome,
        "request_id": context.request_id,
        "route_id": context.route_id,
        "method": context.method,
    }
    if context.actor_user_id:
        data["actor_user_id"] = context.actor_user_id
    if context.tenant_id:
        data["tenant_id"] = context.tenant_id
    if context.client_ip:
        data["client_ip"] = context.client_ip
    if status_code is not None:
        data["status_code"] = int(status_code)

    envelope = {
        "schema_version": 1,
        "event_id": event_id,
        "type": event_type,
        "aggregate_type": "gateway_request",
        "aggregate_id": context.request_id,
        "occurred_at": datetime.now(UTC).isoformat(),
        "data": data,
    }
    return event_id, json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8")


async def _publish(
    publisher: AuditEventPublisher,
    event_type: str,
    context: GatewayAuditContext,
    *,
    status_code: int | None = None,
    outcome: str,
) -> None:
    event_id, payload = _event_payload(
        event_type,
        context,
        status_code=status_code,
        outcome=outcome,
    )
    await publisher.publish(
        f"guardian.{event_type}",
        payload,
        event_id=event_id,
    )


async def execute_with_audit(
    policy: RoutePolicy,
    context: GatewayAuditContext,
    publisher: AuditEventPublisher,
    upstream_call: Callable[[], Awaitable[httpx.Response]],
) -> GatewayExecutionResult:
    if not policy.audit_intent_required:
        response = await upstream_call()
        return GatewayExecutionResult(response=response)

    try:
        await _publish(
            publisher,
            "gateway.request.accepted",
            context,
            outcome="accepted",
        )
    except Exception as exc:
        raise GatewayError(
            503,
            "gateway.audit_unavailable",
            "Required audit intent could not be persisted",
        ) from exc

    try:
        response = await upstream_call()
    except Exception:
        try:
            await _publish(
                publisher,
                "gateway.request.completed",
                context,
                outcome="failure",
            )
        except Exception:
            pass
        raise

    outcome = "success" if 200 <= response.status_code < 400 else "failure"
    try:
        await _publish(
            publisher,
            "gateway.request.completed",
            context,
            status_code=response.status_code,
            outcome=outcome,
        )
    except Exception:
        return GatewayExecutionResult(response=response, completion_audit_failed=True)

    return GatewayExecutionResult(response=response)
