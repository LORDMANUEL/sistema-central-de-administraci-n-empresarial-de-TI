from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

IDENTITY = "http://127.0.0.1:8001"
TENANT = "http://127.0.0.1:8002"
ASSET = "http://127.0.0.1:8003"


def request(method: str, url: str, payload: dict[str, Any] | None = None, token: str | None = None) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = response.read()
            return None if not data else json.loads(data)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc


def wait_ready(url: str, timeout_seconds: int = 120) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = request("GET", url)
            if result and result.get("status") in {"ok", "ready"}:
                return
        except Exception as exc:  # service is still starting
            last_error = exc
        time.sleep(2)
    raise RuntimeError(f"Service did not become ready: {url}; last_error={last_error}")


def main() -> None:
    wait_ready(f"{IDENTITY}/health/ready")
    wait_ready(f"{TENANT}/health/ready")
    wait_ready(f"{ASSET}/health/ready")

    email = "guardian-ci@example.com"
    password = "Guardian-CI-Password-2026!"
    request(
        "POST",
        f"{IDENTITY}/api/v1/auth/bootstrap",
        {"email": email, "display_name": "Guardian CI", "password": password},
    )
    tokens = request("POST", f"{IDENTITY}/api/v1/auth/login", {"email": email, "password": password})
    access_token = tokens["access_token"]

    tenant = request(
        "POST",
        f"{TENANT}/api/v1/tenants",
        {
            "name": "Guardian CI Company",
            "slug": "guardian-ci-company",
            "timezone": "America/Tegucigalpa",
            "locale": "es-HN",
        },
        access_token,
    )
    tenant_id = tenant["id"]
    site = request(
        "POST",
        f"{TENANT}/api/v1/tenants/{tenant_id}/sites",
        {"code": "SPS", "name": "San Pedro Sula"},
        access_token,
    )
    department = request(
        "POST",
        f"{TENANT}/api/v1/tenants/{tenant_id}/departments",
        {"code": "IT", "name": "Tecnologia"},
        access_token,
    )

    asset = request(
        "POST",
        f"{ASSET}/api/v1/assets",
        {
            "tenant_id": tenant_id,
            "site_id": site["id"],
            "department_id": department["id"],
            "asset_type": "computer",
            "display_name": "CI-WS-001",
            "hostname": "ci-ws-001",
            "serial_number": "CI-SERIAL-001",
        },
        access_token,
    )
    asset_id = asset["guardian_asset_id"]
    fetched = request("GET", f"{ASSET}/api/v1/assets/{asset_id}", token=access_token)
    listed = request("GET", f"{ASSET}/api/v1/assets?tenant_id={tenant_id}", token=access_token)

    assert fetched["guardian_asset_id"] == asset_id
    assert fetched["site_id"] == site["id"]
    assert fetched["department_id"] == department["id"]
    assert any(item["guardian_asset_id"] == asset_id for item in listed)
    print(json.dumps({"tenant_id": tenant_id, "site_id": site["id"], "department_id": department["id"], "asset_id": asset_id}))


if __name__ == "__main__":
    main()