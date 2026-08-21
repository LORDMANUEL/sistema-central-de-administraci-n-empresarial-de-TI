import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


def test_validation_errors_use_guardian_error_contract(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'validation.db'}")

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/bootstrap",
            json={"email": "not-an-email", "display_name": "", "password": "short"},
        )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "identity.validation_error"
    assert body["error"]["message"] == "Request validation failed"
    assert body["error"]["request_id"]
    assert isinstance(body["error"]["details"], list)


def test_unknown_route_uses_guardian_error_contract(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'not-found.db'}")

    with TestClient(app) as client:
        response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "common.not_found"
    assert response.json()["error"]["request_id"]


def test_production_rejects_default_jwt_secret():
    with pytest.raises(ValidationError):
        Settings(environment="production")


def test_jwt_secret_must_have_at_least_32_characters():
    with pytest.raises(ValidationError):
        Settings(jwt_secret="too-short")
