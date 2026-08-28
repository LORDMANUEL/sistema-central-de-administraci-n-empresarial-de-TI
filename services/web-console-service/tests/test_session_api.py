import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class FakeGateway:
    def __init__(self):
        self.refreshes = 0
        self.me_statuses = [200]

    def login(self, email, password):
        return {"access_token": "access-secret", "refresh_token": "refresh-secret", "token_type": "bearer"}

    def refresh(self, refresh_token):
        self.refreshes += 1
        return {"access_token": "access-new", "refresh_token": "refresh-new", "token_type": "bearer"}

    def request(self, method, path, *, access_token=None, json=None, params=None):
        if path == "/api/v1/users/me":
            code = self.me_statuses.pop(0) if self.me_statuses else 200
            payload = (
                {"id": "u1", "email": "admin@example.com", "display_name": "Admin", "role": "platform_admin", "is_active": True}
                if code == 200
                else {"error": {"code": "expired"}}
            )
            return httpx.Response(code, json=payload)
        raise AssertionError((method, path))


def app(gateway):
    settings = Settings(cookie_secure=False, session_ttl_seconds=300, max_sessions=10)
    return create_app(settings=settings, gateway=gateway)


def test_login_cookie_is_opaque_httponly_and_body_has_no_guardian_tokens():
    gateway = FakeGateway()
    with TestClient(app(gateway)) as client:
        response = client.post("/console/api/session/login", json={"email": "admin@example.com", "password": "very-secret"})
        assert response.status_code == 200
        body = response.json()
        assert body["user"]["email"] == "admin@example.com"
        serialized = str(body)
        assert "access-secret" not in serialized and "refresh-secret" not in serialized
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "SameSite=strict" in cookie
        assert "access-secret" not in cookie and "refresh-secret" not in cookie


def test_me_refreshes_once_server_side_and_never_exposes_refreshed_tokens():
    gateway = FakeGateway()
    gateway.me_statuses = [200, 401, 200]
    with TestClient(app(gateway)) as client:
        assert client.post("/console/api/session/login", json={"email": "admin@example.com", "password": "very-secret"}).status_code == 200
        response = client.get("/console/api/session/me")
        assert response.status_code == 200 and gateway.refreshes == 1
        assert "access-new" not in response.text and "refresh-new" not in response.text


def test_logout_destroys_session():
    gateway = FakeGateway()
    with TestClient(app(gateway)) as client:
        client.post("/console/api/session/login", json={"email": "admin@example.com", "password": "very-secret"})
        output = client.post("/console/api/session/logout")
        assert output.status_code == 204
        assert client.get("/console/api/session/me").status_code == 401
