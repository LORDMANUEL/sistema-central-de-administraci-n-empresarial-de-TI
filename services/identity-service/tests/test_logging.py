import json
import logging

from fastapi.testclient import TestClient

from app.main import create_app


def test_http_log_is_structured_and_contains_request_id(tmp_path, caplog):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'logging.db'}")
    caplog.set_level(logging.INFO, logger="guardian.identity.http")

    with TestClient(app) as client:
        response = client.get("/health/live", headers={"X-Request-ID": "req-test-123"})

    assert response.status_code == 200
    messages = [json.loads(record.message) for record in caplog.records if record.name == "guardian.identity.http"]
    assert any(
        message["service"] == "identity-service"
        and message["method"] == "GET"
        and message["path"] == "/health/live"
        and message["status"] == 200
        and message["request_id"] == "req-test-123"
        for message in messages
    )
