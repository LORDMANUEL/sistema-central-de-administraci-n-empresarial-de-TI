from fastapi.testclient import TestClient

from app.main import create_app


def test_health_endpoints_are_available(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'asset.db'}", auth_disabled=True)
    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        metrics = client.get("/metrics")

    assert live.status_code == 200
    assert live.json()["status"] == "ok"
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert metrics.status_code == 200
    assert "it_guardian_asset_http_requests_total" in metrics.text
