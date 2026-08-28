import httpx
from fastapi.testclient import TestClient

from app.api.resources import OPERATIONS
from app.config import Settings
from app.main import create_app


class FakeGateway:
    def __init__(self):
        self.calls = []

    def login(self, email, password):
        return {"access_token": "access", "refresh_token": "refresh"}

    def refresh(self, refresh_token):
        return {"access_token": "access2", "refresh_token": "refresh2"}

    def request(self, method, path, *, access_token=None, json=None, params=None):
        self.calls.append((method, path, access_token, json, params))
        if path == "/api/v1/users/me":
            return httpx.Response(200, json={"id": "u", "email": "a@b.c", "display_name": "A", "role": "platform_admin", "is_active": True})
        if path == "/api/v1/devices":
            return httpx.Response(200, json=[{"device_id": "d1", "state": "online"}])
        if path == "/api/v1/commands" and method == "POST":
            return httpx.Response(201, json={"command_id": "c1", "state": "queued"})
        return httpx.Response(404, json={"error": {"code": "missing", "message": "missing"}})


def app(gateway):
    return create_app(
        settings=Settings(cookie_secure=False, session_ttl_seconds=300, max_sessions=10),
        gateway=gateway,
    )


def login(client):
    assert client.post("/console/api/session/login", json={"email": "a@b.c", "password": "secret"}).status_code == 200


def test_operation_registry_is_explicit_and_contains_no_device_plane():
    assert len(OPERATIONS) == 35
    assert all("/device/" not in operation.gateway_path for operation in OPERATIONS)
    assert any(operation.console_path == "/devices" and operation.method == "GET" for operation in OPERATIONS)
    assert any(operation.console_path == "/commands" and operation.method == "POST" for operation in OPERATIONS)
    assert any(operation.console_path == "/audit/verify" and operation.method == "GET" for operation in OPERATIONS)


def test_devices_route_uses_server_side_bearer_only():
    gateway = FakeGateway()
    with TestClient(app(gateway)) as client:
        login(client)
        response = client.get("/console/api/devices")
        assert response.status_code == 200 and response.json()[0]["state"] == "online"
        call = gateway.calls[-1]
        assert call[:3] == ("GET", "/api/v1/devices", "access")


def test_command_create_forwards_json_but_not_browser_authorization():
    gateway = FakeGateway()
    with TestClient(app(gateway)) as client:
        login(client)
        response = client.post(
            "/console/api/commands",
            headers={"Authorization": "Bearer attacker"},
            json={
                "guardian_asset_id": "a",
                "device_id": "d",
                "command_type": "inventory.refresh",
                "arguments": {},
                "idempotency_key": "k",
            },
        )
        assert response.status_code == 201
        call = gateway.calls[-1]
        assert call[0] == "POST" and call[1] == "/api/v1/commands" and call[2] == "access"
        assert call[3]["command_type"] == "inventory.refresh"


def test_device_plane_and_unknown_paths_are_not_registered():
    gateway = FakeGateway()
    with TestClient(app(gateway)) as client:
        login(client)
        assert client.post("/console/api/device/heartbeat", json={}).status_code == 404
        assert client.get("/console/api/not-real").status_code == 404
