from fastapi.testclient import TestClient

from app.main import create_app


def test_metrics_endpoint_exposes_identity_http_counter(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'metrics.db'}")

    with TestClient(app) as client:
        client.get("/health/live")
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "guardian_identity_http_requests_total" in response.text
    assert 'path="/health/live"' in response.text
