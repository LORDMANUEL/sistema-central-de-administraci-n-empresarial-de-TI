from fastapi.testclient import TestClient

from app.main import create_app


def test_live_is_ok_even_without_ca_material(tmp_path):
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'pki.db'}",
        ca_cert_path=str(tmp_path / "missing-cert.pem"),
        ca_key_path=str(tmp_path / "missing-key.pem"),
    )
    with TestClient(app) as client:
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "pki-service"}


def test_ready_is_503_when_online_signer_is_missing(tmp_path):
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'pki.db'}",
        ca_cert_path=str(tmp_path / "missing-cert.pem"),
        ca_key_path=str(tmp_path / "missing-key.pem"),
    )
    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "pki.ca_unavailable"
        assert response.headers["X-Request-ID"]
