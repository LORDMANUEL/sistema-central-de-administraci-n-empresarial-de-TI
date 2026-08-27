from __future__ import annotations

import json
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

GATEWAY = "http://127.0.0.1:8080"
SECRET_MARKER = "GATEWAY-E2E-SECRET-MUST-NOT-PERSIST"


def request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    *,
    extra_headers: dict[str, str] | None = None,
    raw_body: bytes | None = None,
    timeout: int = 20,
) -> tuple[int, Any, dict[str, str]]:
    if raw_body is not None and payload is not None:
        raise ValueError("payload and raw_body are mutually exclusive")
    body = raw_body if raw_body is not None else (None if payload is None else json.dumps(payload).encode("utf-8"))
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(f"{GATEWAY}{path}", data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            response_headers = {key: value for key, value in response.headers.items()}
            if not raw:
                data: Any = None
            elif "json" in response.headers.get("Content-Type", ""):
                data = json.loads(raw)
            else:
                data = raw.decode("utf-8", errors="replace")
            return response.status, data, response_headers
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            data = None if not raw else json.loads(raw)
        except (TypeError, ValueError):
            data = raw.decode("utf-8", errors="replace")
        return exc.code, data, {key: value for key, value in exc.headers.items()}


def require(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    *,
    expected: tuple[int, ...] = (200,),
    extra_headers: dict[str, str] | None = None,
) -> Any:
    status, data, _ = request(method, path, payload, token, extra_headers=extra_headers)
    if status not in expected:
        raise RuntimeError(f"{method} {path} failed: HTTP {status}: {data}")
    return data


def wait_ready(timeout_seconds: int = 240) -> None:
    deadline = time.monotonic() + timeout_seconds
    last: tuple[int, Any, dict[str, str]] | None = None
    while time.monotonic() < deadline:
        try:
            last = request("GET", "/health/ready", timeout=5)
            if last[0] == 200 and last[1] and last[1].get("status") == "ready":
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(f"Gateway did not become ready; last={last}")


def generate_csr(directory: Path, name: str) -> str:
    key = directory / f"{name}.key.pem"
    csr = directory / f"{name}.csr.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-new",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(csr),
            "-subj",
            f"/CN={name}",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return csr.read_text(encoding="utf-8")


def audit_records(tenant_id: str, token: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"tenant_id": tenant_id, "limit": 500})
    return require("GET", f"/api/v1/audit/records?{query}", token=token)["items"]


def wait_for_gateway_audit_pair(tenant_id: str, token: str, request_id: str, timeout_seconds: int = 120):
    deadline = time.monotonic() + timeout_seconds
    last: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        last = audit_records(tenant_id, token)
        accepted = [
            item for item in last
            if item.get("source_type") == "gateway.request.accepted" and item.get("request_id") == request_id
        ]
        completed = [
            item for item in last
            if item.get("source_type") == "gateway.request.completed" and item.get("request_id") == request_id
        ]
        if accepted and completed:
            return accepted[0], completed[0], last
        time.sleep(1)
    raise RuntimeError(f"Gateway audit pair did not arrive: request_id={request_id}; records={len(last)}")


def main() -> None:
    wait_ready()

    email = "gateway-ci@example.com"
    password = "Guardian-Gateway-CI-2026!"
    require(
        "POST",
        "/api/v1/auth/bootstrap",
        {"email": email, "display_name": "Gateway CI", "password": password},
        expected=(201,),
    )
    login = require(
        "POST",
        "/api/v1/auth/login",
        {"email": email, "password": password},
    )
    access_token = login["access_token"]

    # Caller-controlled Guardian headers must never grant access.
    status, denied, _ = request(
        "GET",
        "/api/v1/tenants",
        extra_headers={"X-Guardian-Role": "platform_admin", "X-Guardian-User": "attacker"},
    )
    assert status == 401, (status, denied)
    assert denied["error"]["code"] == "gateway.authentication_required", denied

    tenant = require(
        "POST",
        "/api/v1/tenants",
        {
            "name": "Gateway CI Company",
            "slug": "gateway-ci-company",
            "timezone": "America/Tegucigalpa",
            "locale": "es-HN",
        },
        access_token,
        expected=(201,),
    )
    tenant_id = tenant["id"]

    correlation_id = "gateway-e2e-site-create"
    site = require(
        "POST",
        f"/api/v1/tenants/{tenant_id}/sites",
        {"code": "SPS", "name": "San Pedro Sula"},
        access_token,
        expected=(201,),
        extra_headers={"X-Request-ID": correlation_id, "X-Guardian-Tenant": "spoofed-tenant"},
    )
    department = require(
        "POST",
        f"/api/v1/tenants/{tenant_id}/departments",
        {"code": "IT", "name": "Tecnologia"},
        access_token,
        expected=(201,),
    )
    asset = require(
        "POST",
        "/api/v1/assets",
        {
            "tenant_id": tenant_id,
            "site_id": site["id"],
            "department_id": department["id"],
            "asset_type": "computer",
            "display_name": "Gateway CI Workstation",
            "hostname": "gateway-ci-ws-001",
            "serial_number": "GATEWAY-CI-SERIAL-001",
        },
        access_token,
        expected=(201,),
    )
    asset_id = asset["guardian_asset_id"]

    token_created = require(
        "POST",
        "/api/v1/enrollment-tokens",
        {"tenant_id": tenant_id, "asset_id": asset_id, "expires_in_minutes": 60},
        access_token,
        expected=(201,),
    )
    enrollment_token = token_created["token"]

    with tempfile.TemporaryDirectory(prefix="guardian-gateway-smoke-") as temp:
        csr = generate_csr(Path(temp), "gateway-ci-ws-001")
        enroll_payload = {
            "token": enrollment_token,
            "platform": "windows",
            "hostname": "GATEWAY-CI-WS-001",
            "agent_version": "0.7.0-dev.1",
            "csr_pem": csr,
        }
        enrolled = require(
            "POST",
            "/api/v1/enrollments",
            enroll_payload,
            expected=(201,),
        )
        retry = require(
            "POST",
            "/api/v1/enrollments",
            enroll_payload,
            expected=(200,),
        )
        assert retry["device_id"] == enrolled["device_id"]
        assert retry["certificate_id"] == enrolled["certificate_id"]
        assert retry["certificate_fingerprint_sha256"] == enrolled["certificate_fingerprint_sha256"]

    # Internal/unregistered routes must stay invisible northbound.
    for method, path, payload in (
        ("GET", "/.well-known/jwks.json", None),
        ("GET", f"/api/v1/tenants/{tenant_id}/access", None),
        ("POST", "/api/v1/certificates/issue", {}),
        ("GET", "/_internal/identity/.well-known/jwks.json", None),
    ):
        status, body, _ = request(method, path, payload, access_token if method == "GET" else None)
        assert status == 404, (method, path, status, body)
        assert body["error"]["code"] == "gateway.route_not_allowed", body

    # Oversize JSON is rejected before an upstream call.
    status, body, _ = request(
        "POST",
        "/api/v1/auth/login",
        raw_body=b"{" + (b"x" * (1024 * 1024 + 8)) + b"}",
    )
    assert status == 413, (status, body)
    assert body["error"]["code"] == "gateway.body_too_large", body

    # Strict login bucket: five pass to Identity, sixth is rejected by Gateway.
    limited_email = "gateway-rate-limit@example.com"
    rate_statuses: list[int] = []
    for _ in range(6):
        status, _, headers = request(
            "POST",
            "/api/v1/auth/login",
            {"email": limited_email, "password": "not-a-real-password"},
        )
        rate_statuses.append(status)
    assert rate_statuses[:5] == [401] * 5, rate_statuses
    assert rate_statuses[5] == 429, rate_statuses
    assert int(headers.get("Retry-After", "0")) >= 1, headers

    accepted, completed, records = wait_for_gateway_audit_pair(
        tenant_id,
        access_token,
        correlation_id,
    )
    assert accepted["action"] == "tenant.site.create", accepted
    assert accepted["outcome"] == "accepted", accepted
    assert completed["action"] == "tenant.site.create", completed
    assert completed["outcome"] == "success", completed

    verify_query = urllib.parse.urlencode({"tenant_id": tenant_id})
    chain = require("GET", f"/api/v1/audit/verify?{verify_query}", token=access_token)
    assert chain["valid"] is True, chain

    metrics_status, metrics, _ = request("GET", "/metrics")
    assert metrics_status == 200
    assert "it_guardian_gateway_requests_total" in metrics, metrics[:500]

    serialized_audit = json.dumps(records, sort_keys=True)
    assert SECRET_MARKER not in serialized_audit
    assert "spoofed-tenant" not in serialized_audit

    # Fail-closed proof: no JetStream ACK means no privileged mutation.
    subprocess.run(["docker", "compose", "stop", "nats"], check=True)
    fail_closed_email = "must-not-be-created@example.com"
    try:
        status, failure, _ = request(
            "POST",
            "/api/v1/users",
            {
                "email": fail_closed_email,
                "display_name": "Must Not Exist",
                "role": "viewer",
                "password": SECRET_MARKER,
            },
            access_token,
            timeout=20,
        )
        assert status == 503, (status, failure)
        assert failure["error"]["code"] == "gateway.audit_unavailable", failure

        users = require("GET", "/api/v1/users", token=access_token)
        assert all(item["email"] != fail_closed_email for item in users), users
    finally:
        subprocess.run(["docker", "compose", "start", "nats"], check=True)

    print(
        json.dumps(
            {
                "status": "ok",
                "tenant_id": tenant_id,
                "asset_id": asset_id,
                "device_id": enrolled["device_id"],
                "certificate_id": enrolled["certificate_id"],
                "audit_request_id": correlation_id,
                "audit_chain_valid": True,
                "internal_routes_blocked": True,
                "spoofing_blocked": True,
                "body_limit_verified": True,
                "rate_limit_verified": True,
                "fail_closed_verified": True,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
