import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class FakeGateway:
    def __init__(self):
        self.refreshes = 0
        self.bootstraps = 0
        self.me_statuses = [200]

    def bootstrap(self, email, display_name, password):
        self.bootstraps += 1
        return {"id": "u1", "email": email, "display_name": display_name, "role": "platform_admin", "is_active": True}

    def login(self, email, password):
        return {"access_token": "access-secret", "refresh_token": "refresh-secret", "token_type": "bearer"}

    def refresh(self, refresh_token):
        self.refreshes += 1
        return {"access_token": "access-new", "refresh_token": "refresh-new", "token_type": "bearer"}

    def request(self, method, path, *, access_token=None, json=None, params=None):
        if path == "/api/v1/users/me":
            code = self.me_statuses.pop(0) if self.me_statuses else 200
            payload = ({"id": "u1", "email": "admin@example.com", "display_name": "Admin", "role": "platform_admin", "is_active": True} if code == 200 else {"error": {"code": "expired"}})
            return httpx.Response(code, json=payload)
        if path == "/health/live":
            return httpx.Response(200, json={"status": "ok"})
        raise AssertionError((method, path))


def app(gateway):
    settings = Settings(cookie_secure=False, session_ttl_seconds=300, max_sessions=10)
    return create_app(settings=settings, gateway=gateway)


def test_bootstrap_creates_first_admin_then_establishes_opaque_session():
    gateway = FakeGateway()
    with TestClient(app(gateway)) as client:
        response = client.post("/console/api/session/bootstrap", json={"email": "admin@example.com", "display_name": "Admin", "password": "very-secret-12"})
        assert response.status_code == 201 and gateway.bootstraps == 1
        assert response.json()["user"]["role"] == "platform_admin"
        assert len(response.json()["csrf_token"]) >= 32
        assert "access-secret" not in response.text and "refresh-secret" not in response.text
        assert "HttpOnly" in response.headers["set-cookie"]


def test_login_cookie_is_opaque_httponly_and_body_has_no_guardian_tokens():
    gateway = FakeGateway()
    with TestClient(app(gateway)) as client:
        response = client.post("/console/api/session/login", json={"email": "admin@example.com", "password": "very-secret"})
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["email"] == "admin@example.com"
        assert len(body["csrf_token"]) >= 32
        serialized = str(body)
        assert "access-secret" not in serialized and "refresh-secret" not in serialized
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie
        assert "access-secret" not in cookie and "refresh-secret" not in cookie


def test_me_refreshes_once_server_side_and_never_exposes_refreshed_tokens():
    gateway = FakeGateway()
    gateway.me_statuses = [200, 401, 200]
    with TestClient(app(gateway)) as client:
        login = client.post("/console/api/session/login", json={"email": "admin@example.com", "password": "very-secret"})
        assert login.status_code == 200
        response = client.get("/console/api/session/me")
        assert response.status_code == 200 and gateway.refreshes == 1
        assert len(response.json()["csrf_token"]) >= 32
        assert "access-new" not in response.text and "refresh-new" not in response.text


def test_logout_requires_csrf_and_destroys_session():
    gateway = FakeGateway()
    with TestClient(app(gateway)) as client:
        login = client.post("/console/api/session/login", json={"email": "admin@example.com", "password": "very-secret"})
        csrf = login.json()["csrf_token"]
        assert client.post("/console/api/session/logout").status_code == 403
        output = client.post("/console/api/session/logout", headers={"X-Guardian-CSRF": csrf})
        assert output.status_code == 204
        assert client.get("/console/api/session/me").status_code == 401
