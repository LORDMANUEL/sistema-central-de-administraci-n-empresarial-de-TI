from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_gateway_health_is_local_and_does_not_require_downstream_availability():
    app = create_app(
        settings=Settings(
            identity_service_url="http://127.0.0.1:1",
            tenant_service_url="http://127.0.0.1:1",
            asset_service_url="http://127.0.0.1:1",
            enrollment_service_url="http://127.0.0.1:1",
            pki_service_url="http://127.0.0.1:1",
            audit_service_url="http://127.0.0.1:1",
        )
    )
    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok", "service": "gateway-service"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "service": "gateway-service"}
    assert app.state.route_registry is not None
