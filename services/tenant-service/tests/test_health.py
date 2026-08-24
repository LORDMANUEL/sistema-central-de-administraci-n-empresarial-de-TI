from fastapi.testclient import TestClient

from app.main import create_app


def test_live_and_ready_health_report_tenant_service(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'tenant-health.db'}", jwks={"keys": []})

    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok", "service": "tenant-service"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ok", "service": "tenant-service"}
