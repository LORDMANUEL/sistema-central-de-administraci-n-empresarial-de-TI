from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import httpx
import pytest

from app.audit_publisher import GatewayAuditContext, execute_with_audit
from app.config import Settings
from app.errors import GatewayError
from app.routes import RouteRegistry, build_route_policies


@dataclass
class Published:
    subject: str
    payload: bytes
    event_id: str


class Publisher:
    def __init__(self, *, fail_subject: str | None = None) -> None:
        self.fail_subject = fail_subject
        self.items: list[Published] = []

    async def publish(self, subject: str, payload: bytes, *, event_id: str) -> None:
        if subject == self.fail_subject:
            raise RuntimeError("NATS unavailable with SECRET_SHOULD_NOT_LEAK")
        self.items.append(Published(subject, payload, event_id))


def _policy():
    registry = RouteRegistry(build_route_policies(Settings()))
    return registry.require_northbound("POST", "/api/v1/users").policy


def _context() -> GatewayAuditContext:
    return GatewayAuditContext(
        request_id="req-audit-123",
        route_id="identity.user.create",
        method="POST",
        actor_user_id="user-123",
        tenant_id=None,
        client_ip="192.0.2.10",
    )


def test_required_audit_intent_failure_prevents_upstream_mutation():
    publisher = Publisher(fail_subject="guardian.gateway.request.accepted")
    calls = 0

    async def upstream() -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(201, json={"created": True})

    with pytest.raises(GatewayError) as raised:
        asyncio.run(execute_with_audit(_policy(), _context(), publisher, upstream))

    assert raised.value.status_code == 503
    assert raised.value.code == "gateway.audit_unavailable"
    assert calls == 0


def test_successful_privileged_mutation_publishes_accepted_then_completed_with_same_request_id():
    publisher = Publisher()
    calls = 0

    async def upstream() -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(201, json={"created": True})

    result = asyncio.run(execute_with_audit(_policy(), _context(), publisher, upstream))

    assert result.response.status_code == 201
    assert result.completion_audit_failed is False
    assert calls == 1
    assert [item.subject for item in publisher.items] == [
        "guardian.gateway.request.accepted",
        "guardian.gateway.request.completed",
    ]

    accepted = json.loads(publisher.items[0].payload)
    completed = json.loads(publisher.items[1].payload)
    assert accepted["type"] == "gateway.request.accepted"
    assert completed["type"] == "gateway.request.completed"
    assert accepted["data"]["request_id"] == "req-audit-123"
    assert completed["data"]["request_id"] == "req-audit-123"
    assert completed["data"]["status_code"] == 201
    assert accepted["aggregate_id"] == completed["aggregate_id"] == "req-audit-123"


def test_completed_audit_failure_never_retries_already_executed_mutation():
    publisher = Publisher(fail_subject="guardian.gateway.request.completed")
    calls = 0

    async def upstream() -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(204)

    result = asyncio.run(execute_with_audit(_policy(), _context(), publisher, upstream))

    assert result.response.status_code == 204
    assert result.completion_audit_failed is True
    assert calls == 1


def test_gateway_audit_events_have_no_arbitrary_request_body_or_credentials_fields():
    publisher = Publisher()

    async def upstream() -> httpx.Response:
        return httpx.Response(200)

    asyncio.run(execute_with_audit(_policy(), _context(), publisher, upstream))
    serialized = b"\n".join(item.payload for item in publisher.items).decode("utf-8").lower()

    for forbidden in (
        "authorization",
        "bearer ",
        "password",
        "private_key",
        "signing_key",
        "csr_pem",
        "token_hash",
        "access_token",
        "refresh_token",
        "secret_should_not_leak",
    ):
        assert forbidden not in serialized
