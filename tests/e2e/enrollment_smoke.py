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

IDENTITY = "http://127.0.0.1:8001"
TENANT = "http://127.0.0.1:8002"
ASSET = "http://127.0.0.1:8003"
PKI = "http://127.0.0.1:8004"
ENROLLMENT = "http://127.0.0.1:8005"


def request(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
) -> tuple[int, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            raw = response.read()
            data = None if not raw else json.loads(raw)
            return response.status, data
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        data = None if not raw else json.loads(raw)
        return exc.code, data


def require(method: str, url: str, payload=None, token: str | None = None, expected=(200,)) -> Any:
    status, data = request(method, url, payload, token)
    if status not in expected:
        raise RuntimeError(f"{method} {url} failed: HTTP {status}: {data}")
    return data


def wait_ready(url: str, timeout_seconds: int = 180) -> None:
    deadline = time.monotonic() + timeout_seconds
    last: tuple[int, Any] | None = None
    while time.monotonic() < deadline:
        try:
            last = request("GET", url)
            if last[0] == 200 and last[1] and last[1].get("status") in {"ok", "ready"}:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(f"Service did not become ready: {url}; last={last}")


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


def verify_certificate(pem: str, expected_cn: str, directory: Path) -> None:
    cert = directory / "device-cert.pem"
    cert.write_text(pem, encoding="utf-8")
    subject = subprocess.check_output(
        ["openssl", "x509", "-in", str(cert), "-noout", "-subject"],
        text=True,
    )
    assert expected_cn in subject, subject
    subprocess.run(
        ["openssl", "x509", "-in", str(cert), "-noout", "-checkend", "1"],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def main() -> None:
    for endpoint in (
        f"{IDENTITY}/health/ready",
        f"{TENANT}/health/ready",
        f"{ASSET}/health/ready",
        f"{ENROLLMENT}/health/ready",
        f"{PKI}/health/ready",
    ):
        wait_ready(endpoint)

    email = "enrollment-ci@example.com"
    password = "Guardian-Enrollment-CI-2026!"
    require(
        "POST",
        f"{IDENTITY}/api/v1/auth/bootstrap",
        {"email": email, "display_name": "Enrollment CI", "password": password},
        expected=(201,),
    )
    login = require(
        "POST",
        f"{IDENTITY}/api/v1/auth/login",
        {"email": email, "password": password},
        expected=(200,),
    )
    access_token = login["access_token"]

    tenant = require(
        "POST",
        f"{TENANT}/api/v1/tenants",
        {
            "name": "Enrollment CI Company",
            "slug": "enrollment-ci-company",
            "timezone": "America/Tegucigalpa",
            "locale": "es-HN",
        },
        access_token,
        expected=(201,),
    )
    tenant_id = tenant["id"]
    site = require(
        "POST",
        f"{TENANT}/api/v1/tenants/{tenant_id}/sites",
        {"code": "SPS", "name": "San Pedro Sula"},
        access_token,
        expected=(201,),
    )
    department = require(
        "POST",
        f"{TENANT}/api/v1/tenants/{tenant_id}/departments",
        {"code": "IT", "name": "Tecnologia"},
        access_token,
        expected=(201,),
    )
    asset = require(
        "POST",
        f"{ASSET}/api/v1/assets",
        {
            "tenant_id": tenant_id,
            "site_id": site["id"],
            "department_id": department["id"],
            "asset_type": "computer",
            "display_name": "Enrollment CI Workstation",
            "hostname": "ci-enroll-ws-001",
            "serial_number": "CI-ENROLL-SERIAL-001",
        },
        access_token,
        expected=(201,),
    )
    asset_id = asset["guardian_asset_id"]

    token_created = require(
        "POST",
        f"{ENROLLMENT}/api/v1/enrollment-tokens",
        {"tenant_id": tenant_id, "asset_id": asset_id, "expires_in_minutes": 60},
        access_token,
        expected=(201,),
    )
    enrollment_token = token_created["token"]
    token_id = token_created["id"]
    assert enrollment_token.startswith("gdt_")
    assert "token_hash" not in token_created

    with tempfile.TemporaryDirectory(prefix="guardian-enrollment-smoke-") as temp:
        directory = Path(temp)
        csr_one = generate_csr(directory, "ci-enroll-ws-001")
        payload = {
            "token": enrollment_token,
            "platform": "windows",
            "hostname": "CI-ENROLL-WS-001",
            "agent_version": "0.7.0-dev.1",
            "csr_pem": csr_one,
        }
        first = require(
            "POST",
            f"{ENROLLMENT}/api/v1/enrollments",
            payload,
            expected=(201,),
        )
        retry = require(
            "POST",
            f"{ENROLLMENT}/api/v1/enrollments",
            payload,
            expected=(200,),
        )
        for key in (
            "device_id",
            "certificate_id",
            "certificate_serial_hex",
            "certificate_fingerprint_sha256",
            "certificate_pem",
            "ca_chain_pem",
        ):
            assert first[key] == retry[key], (key, first[key], retry[key])
        assert first["tenant_id"] == tenant_id
        assert first["asset_id"] == asset_id
        assert "private_key" not in first
        assert "grant" not in first
        verify_certificate(first["certificate_pem"], "ci-enroll-ws-001", directory)

        csr_two = generate_csr(directory, "ci-enroll-ws-002")
        replay_status, replay = request(
            "POST",
            f"{ENROLLMENT}/api/v1/enrollments",
            {**payload, "csr_pem": csr_two},
        )
        assert replay_status == 409, replay
        assert replay["error"]["code"] == "enrollment.token_replay", replay

    query = urllib.parse.urlencode({"tenant_id": tenant_id})
    tokens = require(
        "GET",
        f"{ENROLLMENT}/api/v1/enrollment-tokens?{query}",
        token=access_token,
        expected=(200,),
    )
    stored_token = next(item for item in tokens if item["id"] == token_id)
    assert stored_token["status"] == "consumed", stored_token
    assert "token" not in stored_token
    assert "token_hash" not in stored_token

    inventory = require(
        "GET",
        f"{ENROLLMENT}/api/v1/enrollments?{query}",
        token=access_token,
        expected=(200,),
    )
    device_id = first["device_id"]
    item = next(entry for entry in inventory if entry["device_id"] == device_id)
    assert item["status"] == "enrolled", item
    forbidden = {"token_id", "token_hash", "request_fingerprint", "csr_sha256", "certificate_pem", "ca_chain_pem"}
    assert not forbidden.intersection(item), item

    detail = require(
        "GET",
        f"{ENROLLMENT}/api/v1/enrollments/{device_id}",
        token=access_token,
        expected=(200,),
    )
    assert detail == item

    print(
        json.dumps(
            {
                "tenant_id": tenant_id,
                "asset_id": asset_id,
                "token_id": token_id,
                "device_id": device_id,
                "certificate_id": first["certificate_id"],
                "certificate_fingerprint_sha256": first["certificate_fingerprint_sha256"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
