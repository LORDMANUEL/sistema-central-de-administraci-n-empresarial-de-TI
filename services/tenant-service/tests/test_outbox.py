import asyncio
import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import OutboxEvent
from app.outbox_worker import publish_pending_once


class RecordingPublisher:
    def __init__(self, fail=False):
        self.fail = fail
        self.messages = []

    async def publish(self, subject: str, payload: bytes) -> None:
        self.messages.append((subject, payload))
        if self.fail:
            raise RuntimeError("nats unavailable")


def create_tenant(client, headers):
    response = client.post(
        "/api/v1/tenants",
        headers=headers,
        json={"name": "ACME", "slug": "acme", "timezone": "UTC", "locale": "es-HN"},
    )
    assert response.status_code == 201
    return response.json()


def test_tenant_mutation_writes_domain_event_in_same_database(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'outbox-create.db'}", jwks=jwks)

    with TestClient(app) as client:
        tenant = create_tenant(client, auth_header())

    with app.state.database.session_factory() as session:
        events = list(session.scalars(select(OutboxEvent)).all())

    assert len(events) == 1
    assert events[0].event_type == "tenant.created"
    assert events[0].aggregate_id == tenant["id"]
    assert events[0].payload["tenant_id"] == tenant["id"]
    assert events[0].published_at is None


def test_duplicate_tenant_rollback_does_not_leave_phantom_event(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'outbox-rollback.db'}", jwks=jwks)
    headers = auth_header()

    with TestClient(app) as client:
        create_tenant(client, headers)
        duplicate = client.post(
            "/api/v1/tenants",
            headers=headers,
            json={"name": "Other", "slug": "acme", "timezone": "UTC", "locale": "es-HN"},
        )
        assert duplicate.status_code == 409

    with app.state.database.session_factory() as session:
        events = list(session.scalars(select(OutboxEvent)).all())
    assert [event.event_type for event in events] == ["tenant.created"]


def test_outbox_worker_marks_event_only_after_publisher_ack(tmp_path, identity_crypto, auth_header):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'outbox-publish.db'}", jwks=jwks)

    with TestClient(app) as client:
        tenant = create_tenant(client, auth_header())

    failing = RecordingPublisher(fail=True)
    first_result = asyncio.run(publish_pending_once(app.state.database, failing, batch_size=10))
    assert first_result == {"published": 0, "failed": 1}

    with app.state.database.session_factory() as session:
        pending = session.scalar(select(OutboxEvent))
        assert pending.published_at is None
        assert pending.attempts == 1
        assert "nats unavailable" in pending.last_error

    healthy = RecordingPublisher()
    second_result = asyncio.run(publish_pending_once(app.state.database, healthy, batch_size=10))
    assert second_result == {"published": 1, "failed": 0}
    subject, payload = healthy.messages[0]
    envelope = json.loads(payload)
    assert subject == "guardian.tenant.created"
    assert envelope["event_id"]
    assert envelope["type"] == "tenant.created"
    assert envelope["aggregate_id"] == tenant["id"]
    assert envelope["data"]["tenant_id"] == tenant["id"]

    with app.state.database.session_factory() as session:
        published = session.scalar(select(OutboxEvent))
        assert published.published_at is not None
        assert published.attempts == 2
        assert published.last_error is None
