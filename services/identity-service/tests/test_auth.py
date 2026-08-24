from fastapi.testclient import TestClient

from app.main import create_app
from app.models import User


ADMIN = {
    "email": "admin@example.com",
    "display_name": "Platform Admin",
    "password": "Correct-Horse-Battery-Staple-2026!",
}


def _new_client(tmp_path, name="auth.db"):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / name}")
    return app, TestClient(app)


def test_login_returns_typed_access_and_refresh_tokens(tmp_path):
    app, client = _new_client(tmp_path)
    with client:
        client.post("/api/v1/auth/bootstrap", json=ADMIN)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN["email"], "password": ADMIN["password"]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["access_token"] != body["refresh_token"]


def test_login_rejects_wrong_password_with_stable_error(tmp_path):
    _, client = _new_client(tmp_path, "wrong-password.db")
    with client:
        client.post("/api/v1/auth/bootstrap", json=ADMIN)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN["email"], "password": "not-the-password"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "identity.invalid_credentials"
    assert response.json()["error"]["request_id"]


def test_refresh_exchanges_refresh_token_for_new_pair(tmp_path):
    _, client = _new_client(tmp_path, "refresh.db")
    with client:
        client.post("/api/v1/auth/bootstrap", json=ADMIN)
        login = client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN["email"], "password": ADMIN["password"]},
        ).json()
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login["refresh_token"]},
        )

    assert response.status_code == 200
    refreshed = response.json()
    assert refreshed["access_token"]
    assert refreshed["refresh_token"]
    assert refreshed["access_token"] != login["access_token"]
    assert refreshed["refresh_token"] != login["refresh_token"]


def test_refresh_rejects_access_token(tmp_path):
    _, client = _new_client(tmp_path, "wrong-token-type.db")
    with client:
        client.post("/api/v1/auth/bootstrap", json=ADMIN)
        login = client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN["email"], "password": ADMIN["password"]},
        ).json()
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login["access_token"]},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "identity.invalid_token_type"


def test_disabled_user_cannot_login_or_refresh(tmp_path):
    app, client = _new_client(tmp_path, "disabled.db")
    with client:
        user_body = client.post("/api/v1/auth/bootstrap", json=ADMIN).json()
        login = client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN["email"], "password": ADMIN["password"]},
        ).json()

        with app.state.database.session_factory() as session:
            user = session.get(User, user_body["id"])
            user.is_active = False
            session.commit()

        login_after_disable = client.post(
            "/api/v1/auth/login",
            json={"email": ADMIN["email"], "password": ADMIN["password"]},
        )
        refresh_after_disable = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login["refresh_token"]},
        )

    assert login_after_disable.status_code == 403
    assert login_after_disable.json()["error"]["code"] == "identity.user_disabled"
    assert refresh_after_disable.status_code == 403
    assert refresh_after_disable.json()["error"]["code"] == "identity.user_disabled"
