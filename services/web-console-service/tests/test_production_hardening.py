import httpx
import fakeredis
from fastapi.testclient import TestClient

from app import session as session_module
from app.config import Settings
from app.main import create_app


class FakeGateway:
    def login(self, email, password):
        return {"access_token": "access", "refresh_token": "refresh"}

    def refresh(self, refresh_token):
        return {"access_token": "access2", "refresh_token": "refresh2"}

    def request(self, method, path, *, access_token=None, json=None, params=None):
        if path == "/api/v1/users/me":
            return httpx.Response(200, json={"id": "u", "email": "admin@example.com", "display_name": "Admin", "role": "platform_admin", "is_active": True})
        if path == "/api/v1/commands" and method == "POST":
            return httpx.Response(201, json={"command_id": "c", "state": "queued"})
        if path == "/health/live":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404, json={"error": {"code": "missing", "message": "missing"}})


def test_redis_session_store_is_shared_and_preserves_csrf_across_instances():
    assert hasattr(session_module, "RedisSessionStore"), "production Redis session store is required"
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    store_type = session_module.RedisSessionStore
    first = store_type(redis_client, ttl_seconds=300, max_sessions=10)
    second = store_type(redis_client, ttl_seconds=300, max_sessions=10)

    session_id = first.create("access-a", "refresh-a")
    from_second = second.get(session_id)
    assert from_second is not None
    assert from_second.access_token == "access-a"
    assert from_second.refresh_token == "refresh-a"
    assert len(from_second.csrf_token) >= 32

    assert second.replace_tokens(session_id, "access-b", "refresh-b") is True
    from_first = first.get(session_id)
    assert from_first is not None
    assert from_first.access_token == "access-b"
    assert from_first.csrf_token == from_second.csrf_token


def test_mutation_requires_session_csrf_and_security_headers_are_always_present():
    settings = Settings(cookie_secure=False, session_ttl_seconds=300, max_sessions=10, max_json_body_bytes=262144)
    with TestClient(create_app(settings=settings, gateway=FakeGateway())) as client:
        login = client.post("/console/api/session/login", json={"email": "admin@example.com", "password": "secret"})
        assert login.status_code == 200
        csrf = login.json().get("csrf_token")
        assert isinstance(csrf, str) and len(csrf) >= 32

        rejected = client.post("/console/api/commands", json={"command_type": "inventory.refresh"})
        assert rejected.status_code == 403
        assert rejected.json()["error"]["code"] == "console.csrf_invalid"

        accepted = client.post(
            "/console/api/commands",
            headers={"X-Guardian-CSRF": csrf},
            json={"command_type": "inventory.refresh"},
        )
        assert accepted.status_code == 201
        assert accepted.headers["cache-control"] == "no-store"
        assert accepted.headers["x-content-type-options"] == "nosniff"
        assert accepted.headers["x-frame-options"] == "DENY"
        assert "default-src 'self'" in accepted.headers["content-security-policy"]


def test_console_rejects_oversized_json_before_gateway_call():
    settings = Settings(cookie_secure=False, session_ttl_seconds=300, max_sessions=10, max_json_body_bytes=1024)
    gateway = FakeGateway()
    with TestClient(create_app(settings=settings, gateway=gateway)) as client:
        login = client.post("/console/api/session/login", json={"email": "admin@example.com", "password": "secret"})
        csrf = login.json()["csrf_token"]
        response = client.post(
            "/console/api/commands",
            headers={"X-Guardian-CSRF": csrf, "Content-Type": "application/json"},
            content=b'"' + b'x' * 2048 + b'"',
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "console.body_too_large"
