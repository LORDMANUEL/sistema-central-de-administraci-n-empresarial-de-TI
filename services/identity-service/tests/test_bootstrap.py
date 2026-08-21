from fastapi.testclient import TestClient

from app.main import create_app


BOOTSTRAP_PAYLOAD = {
    "email": "admin@example.com",
    "display_name": "Platform Admin",
    "password": "Correct-Horse-Battery-Staple-2026!",
}


def test_bootstrap_creates_first_platform_admin_without_exposing_hash(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'bootstrap.db'}")

    with TestClient(app) as client:
        response = client.post("/api/v1/auth/bootstrap", json=BOOTSTRAP_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "admin@example.com"
    assert body["display_name"] == "Platform Admin"
    assert body["role"] == "platform_admin"
    assert body["is_active"] is True
    assert "password" not in body
    assert "password_hash" not in body
    assert body["id"]


def test_bootstrap_is_one_time_only(tmp_path):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'bootstrap-once.db'}")

    with TestClient(app) as client:
        first = client.post("/api/v1/auth/bootstrap", json=BOOTSTRAP_PAYLOAD)
        second = client.post(
            "/api/v1/auth/bootstrap",
            json={**BOOTSTRAP_PAYLOAD, "email": "other@example.com"},
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "identity.bootstrap_already_completed"
    assert second.json()["error"]["message"] == "Identity bootstrap has already been completed"
    assert second.json()["error"]["request_id"]


def test_bootstrap_remains_closed_even_if_first_user_row_is_removed(tmp_path):
    from sqlalchemy import delete

    from app.models import User

    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / 'bootstrap-state.db'}")

    with TestClient(app) as client:
        first = client.post("/api/v1/auth/bootstrap", json=BOOTSTRAP_PAYLOAD)
        assert first.status_code == 201

        with app.state.database.session_factory() as session:
            session.execute(delete(User))
            session.commit()

        second = client.post(
            "/api/v1/auth/bootstrap",
            json={**BOOTSTRAP_PAYLOAD, "email": "replacement@example.com"},
        )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "identity.bootstrap_already_completed"
