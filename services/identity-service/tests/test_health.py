from fastapi.testclient import TestClient

from app.main import create_app


def test_live_and_ready_health_endpoints_report_identity_service(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'health.db'}")

    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok", "service": "identity-service"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ok", "service": "identity-service"}
