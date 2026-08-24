import httpx
import pytest

from app.asset_client import AssetClient, validate_asset_tenant
from app.errors import GuardianError


def _response(status: int, *, json_body=None) -> httpx.Response:
    request = httpx.Request("GET", "http://asset-service:8000/api/v1/assets/asset-1")
    return httpx.Response(status, json=json_body, request=request)


def test_asset_client_fetches_asset_and_forwards_bearer(monkeypatch):
    seen = {}

    def fake_get(url, *, headers, timeout):
        seen.update(url=url, headers=headers, timeout=timeout)
        return _response(
            200,
            json_body={
                "guardian_asset_id": "asset-1",
                "tenant_id": "tenant-1",
                "asset_type": "computer",
                "display_name": "WS-001",
                "status": "active",
                "site_id": None,
                "department_id": None,
                "hostname": "ws-001",
                "serial_number": "SN-001",
                "created_at": "2026-08-24T00:00:00Z",
                "updated_at": "2026-08-24T00:00:00Z",
            },
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    asset = AssetClient("http://asset-service:8000", timeout_seconds=3).get("asset-1", "admin-token")

    assert asset.asset_id == "asset-1"
    assert asset.tenant_id == "tenant-1"
    assert asset.status == "active"
    assert seen["url"].endswith("/api/v1/assets/asset-1")
    assert seen["headers"] == {"Authorization": "Bearer admin-token"}
    assert seen["timeout"] == 3


def test_asset_client_normalizes_not_found_forbidden_and_upstream_failure(monkeypatch):
    client = AssetClient("http://asset-service:8000")

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _response(404, json_body={}))
    with pytest.raises(GuardianError) as raised:
        client.get("asset-1", "token")
    assert raised.value.code == "enrollment.asset_not_found"

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _response(403, json_body={}))
    with pytest.raises(GuardianError) as raised:
        client.get("asset-1", "token")
    assert raised.value.code == "enrollment.access_denied"

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _response(503, json_body={}))
    with pytest.raises(GuardianError) as raised:
        client.get("asset-1", "token")
    assert raised.value.code == "enrollment.asset_service_unavailable"


def test_asset_client_normalizes_network_failure(monkeypatch):
    def failing_get(*args, **kwargs):
        raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(httpx, "get", failing_get)
    with pytest.raises(GuardianError) as raised:
        AssetClient("http://asset-service:8000").get("asset-1", "token")
    assert raised.value.code == "enrollment.asset_service_unavailable"


def test_asset_tenant_binding_rejects_cross_tenant_reference():
    asset = type("Asset", (), {"tenant_id": "tenant-2"})()
    with pytest.raises(GuardianError) as raised:
        validate_asset_tenant(asset, "tenant-1")
    assert raised.value.code == "enrollment.asset_tenant_mismatch"
