from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.consumer import ingest_message
from app.main import create_app
from app.metrics import render_metrics
from app.models import Base


class FakeMessage:
    def __init__(self, payload: dict | bytes) -> None:
        self.data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.acked = False

    async def ack(self):
        self.acked = True


def event(event_id: str):
    return {
        "schema_version": 1,
        "event_id": event_id,
        "type": "asset.created",
        "aggregate_type": "asset",
        "aggregate_id": "asset-1",
        "occurred_at": "2026-08-24T12:00:00Z",
        "data": {
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "hostname": "WS-001",
        },
    }


def test_metrics_endpoint_exists_and_exposes_audit_http_counter(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'audit-metrics.db'}")
    with TestClient(app) as client:
        client.get("/health/live")
        response = client.get("/metrics")
    assert response.status_code == 200
    text = response.text
    assert "it_guardian_audit_http_requests_total" in text


def test_http_log_never_contains_authorization_or_request_body_secret(tmp_path, caplog):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'audit-log.db'}")
    caplog.set_level(logging.INFO, logger="guardian.audit.http")
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/does-not-exist",
            headers={"Authorization": "Bearer AUTHORIZATION-SECRET-MARKER"},
            json={"password": "BODY-SECRET-MARKER"},
        )
    assert response.status_code == 404
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "AUTHORIZATION-SECRET-MARKER" not in rendered
    assert "BODY-SECRET-MARKER" not in rendered
    assert "password" not in rendered.lower()
    assert "does-not-exist" not in rendered
    assert '"path":"<unmatched>"' in rendered


@pytest.mark.asyncio
async def test_consumer_metrics_count_insert_duplicate_and_failure():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    inserted = await ingest_message(session_factory, FakeMessage(event("obs-event-1")))
    duplicate = await ingest_message(session_factory, FakeMessage(event("obs-event-1")))
    failed = await ingest_message(session_factory, FakeMessage(b"not-json"))
    assert inserted.status == "inserted"
    assert duplicate.status == "duplicate"
    assert failed.status == "failed"

    text = render_metrics()[0].decode("utf-8")
    assert "it_guardian_audit_events_received_total" in text
    assert "it_guardian_audit_events_inserted_total" in text
    assert "it_guardian_audit_events_duplicate_total" in text
    assert "it_guardian_audit_events_failed_total" in text
    engine.dispose()


@pytest.mark.asyncio
async def test_consumer_database_exception_message_is_not_logged(caplog):
    class BrokenFactory:
        def __call__(self):
            raise RuntimeError("DB-SECRET-MARKER")

    caplog.set_level(logging.ERROR, logger="guardian.audit.consumer")
    result = await ingest_message(BrokenFactory(), FakeMessage(event("obs-event-db-fail")))
    assert result.status == "failed"
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "DB-SECRET-MARKER" not in rendered
