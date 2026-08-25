from fastapi.testclient import TestClient

from app.main import create_app


def test_health_live_reports_audit_service(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'audit-health.db'}")
    with TestClient(app) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "audit-service"}


def test_health_ready_checks_database(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'audit-ready.db'}")
    with TestClient(app) as client:
        response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "audit-service"}


def test_guardian_error_envelope_contains_request_id(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'audit-error.db'}")
    with TestClient(app) as client:
        response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "audit.not_found"
    assert body["error"]["message"] == "Resource not found"
    assert body["error"]["request_id"]
