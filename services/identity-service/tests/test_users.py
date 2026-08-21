from fastapi.testclient import TestClient

from app.main import create_app


ADMIN = {
    "email": "admin@example.com",
    "display_name": "Platform Admin",
    "password": "Correct-Horse-Battery-Staple-2026!",
}


def _auth(client, email, password):
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_app_client(tmp_path, name):
    app = create_app(database_url=f"sqlite+pysqlite:///{tmp_path / name}")
    return app, TestClient(app)


def test_current_user_returns_authenticated_profile(tmp_path):
    _, client = _create_app_client(tmp_path, "me.db")
    with client:
        created = client.post("/api/v1/auth/bootstrap", json=ADMIN).json()
        headers = _auth(client, ADMIN["email"], ADMIN["password"])
        response = client.get("/api/v1/users/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]
    assert response.json()["role"] == "platform_admin"


def test_platform_admin_can_create_list_and_disable_user(tmp_path):
    _, client = _create_app_client(tmp_path, "manage.db")
    with client:
        client.post("/api/v1/auth/bootstrap", json=ADMIN)
        headers = _auth(client, ADMIN["email"], ADMIN["password"])

        create = client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "email": "helpdesk@example.com",
                "display_name": "Help Desk",
                "password": "Another-Strong-Password-2026!",
                "role": "helpdesk",
            },
        )
        listing = client.get("/api/v1/users", headers=headers)
        disable = client.patch(
            f"/api/v1/users/{create.json()['id']}/status",
            headers=headers,
            json={"is_active": False},
        )

    assert create.status_code == 201
    assert create.json()["role"] == "helpdesk"
    assert {user["email"] for user in listing.json()} == {"admin@example.com", "helpdesk@example.com"}
    assert disable.status_code == 200
    assert disable.json()["is_active"] is False


def test_duplicate_email_returns_conflict(tmp_path):
    _, client = _create_app_client(tmp_path, "duplicate.db")
    with client:
        client.post("/api/v1/auth/bootstrap", json=ADMIN)
        headers = _auth(client, ADMIN["email"], ADMIN["password"])
        payload = {
            "email": "duplicate@example.com",
            "display_name": "Duplicate",
            "password": "Another-Strong-Password-2026!",
            "role": "viewer",
        }
        first = client.post("/api/v1/users", headers=headers, json=payload)
        second = client.post("/api/v1/users", headers=headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "identity.email_already_exists"


def test_non_admin_user_cannot_manage_users(tmp_path):
    _, client = _create_app_client(tmp_path, "forbidden.db")
    with client:
        client.post("/api/v1/auth/bootstrap", json=ADMIN)
        admin_headers = _auth(client, ADMIN["email"], ADMIN["password"])
        client.post(
            "/api/v1/users",
            headers=admin_headers,
            json={
                "email": "viewer@example.com",
                "display_name": "Viewer",
                "password": "Viewer-Strong-Password-2026!",
                "role": "viewer",
            },
        )
        viewer_headers = _auth(client, "viewer@example.com", "Viewer-Strong-Password-2026!")
        response = client.get("/api/v1/users", headers=viewer_headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "identity.forbidden"


def test_missing_bearer_token_returns_stable_auth_error(tmp_path):
    _, client = _create_app_client(tmp_path, "missing-token.db")
    with client:
        client.post("/api/v1/auth/bootstrap", json=ADMIN)
        response = client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "identity.authentication_required"
