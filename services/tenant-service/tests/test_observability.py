import json
import logging

from fastapi.testclient import TestClient

from app.main import create_app


def test_metrics_expose_tenant_http_counter(tmp_path, identity_crypto):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'metrics.db'}", jwks=jwks)

    with TestClient(app) as client:
        client.get("/health/live")
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "guardian_tenant_http_requests_total" in response.text
    assert 'path="/health/live"' in response.text


def test_http_log_is_structured_and_propagates_request_id(tmp_path, identity_crypto, caplog):
    jwks, _ = identity_crypto
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'logging.db'}", jwks=jwks)
    caplog.set_level(logging.INFO, logger="guardian.tenant.http")

    with TestClient(app) as client:
        response = client.get("/health/live", headers={"X-Request-ID": "tenant-req-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "tenant-req-123"
    messages = [json.loads(record.message) for record in caplog.records if record.name == "guardian.tenant.http"]
    assert any(
        message["service"] == "tenant-service"
        and message["request_id"] == "tenant-req-123"
        and message["method"] == "GET"
        and message["path"] == "/health/live"
        and message["status"] == 200
        for message in messages
    )
