from __future__ import annotations

import json
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from gateway_audit_smoke import generate_csr, require as gateway_require, wait_ready as wait_gateway_ready
from v06_agent_command_telemetry_smoke import wait_for_audit_event

EDGE = "https://localhost:8443"
PKI = "http://127.0.0.1:8004"


def http_json(
    base: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    token: str | None = None,
    context: ssl.SSLContext | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> tuple[int, Any, dict[str, str]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(f"{base}{path}", data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as response:
            raw = response.read()
            data: Any = None
            if raw:
                if "json" in response.headers.get("Content-Type", ""):
                    data = json.loads(raw)
                else:
                    data = raw.decode("utf-8", errors="replace")
            return response.status, data, {k: v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            data = None if not raw else json.loads(raw)
        except (TypeError, ValueError):
            data = raw.decode("utf-8", errors="replace")
        return exc.code, data, {k: v for k, v in exc.headers.items()}


def edge_require(
    context: ssl.SSLContext,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    expected: tuple[int, ...] = (200,),
    extra_headers: dict[str, str] | None = None,
) -> Any:
    status, data, _ = http_json(EDGE, method, path, payload, context=context, extra_headers=extra_headers)
    if status not in expected:
        raise RuntimeError(f"Device Edge {method} {path} failed: HTTP {status}: {data}")
    return data


def wait_edge_ready(context: ssl.SSLContext, timeout_seconds: int = 90) -> None:
    deadline = time.monotonic() + timeout_seconds
    last: tuple[int, Any, dict[str, str]] | None = None
    while time.monotonic() < deadline:
        try:
            last = http_json(EDGE, "GET", "/health/ready", context=context, timeout=5)
            if last[0] == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(f"Device Edge did not become ready; last={last}")


def make_mtls_context(temp: Path, enrolled: dict[str, Any], key_path: Path) -> ssl.SSLContext:
    server_ca = temp / "device-edge-server-ca.pem"
    subprocess.run(
        [
            "docker", "compose", "cp",
            "device-edge-service:/var/lib/guardian/device-edge-tls/server-ca.pem",
            str(server_ca),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    client_chain = temp / "device-client-chain.pem"
    client_chain.write_text(
        enrolled["certificate_pem"] + enrolled["ca_chain_pem"],
        encoding="utf-8",
    )
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(server_ca))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=str(client_chain), keyfile=str(key_path))
    return context


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


def main() -> None:
    wait_gateway_ready()
    email = "v07-edge-ci@example.com"
    password = "Guardian-v07-Edge-CI-2026!"
    gateway_require(
        "POST", "/api/v1/auth/bootstrap",
        {"email": email, "display_name": "v0.7 Device Edge CI", "password": password},
        expected=(201,),
    )
    access_token = gateway_require(
        "POST", "/api/v1/auth/login", {"email": email, "password": password}
    )["access_token"]
    tenant = gateway_require(
        "POST", "/api/v1/tenants",
        {"name": "Guardian v07 CI", "slug": "guardian-v07-ci", "timezone": "America/Tegucigalpa", "locale": "es-HN"},
        access_token, expected=(201,),
    )
    tenant_id = tenant["id"]
    site = gateway_require(
        "POST", f"/api/v1/tenants/{tenant_id}/sites",
        {"code": "SPS", "name": "San Pedro Sula"}, access_token, expected=(201,),
    )
    department = gateway_require(
        "POST", f"/api/v1/tenants/{tenant_id}/departments",
        {"code": "IT", "name": "Tecnologia"}, access_token, expected=(201,),
    )
    asset = gateway_require(
        "POST", "/api/v1/assets",
        {
            "tenant_id": tenant_id,
            "site_id": site["id"],
            "department_id": department["id"],
            "asset_type": "computer",
            "display_name": "Guardian v0.7 mTLS endpoint",
            "hostname": "guardian-v07-edge-001",
            "serial_number": "GUARDIAN-V07-EDGE-001",
        },
        access_token, expected=(201,),
    )
    asset_id = asset["guardian_asset_id"]
    token_result = gateway_require(
        "POST", "/api/v1/enrollment-tokens",
        {"tenant_id": tenant_id, "asset_id": asset_id, "expires_in_minutes": 60},
        access_token, expected=(201,),
    )
    enrollment_token = token_result["token"]

    with tempfile.TemporaryDirectory(prefix="guardian-v07-edge-") as raw_temp:
        temp = Path(raw_temp)
        hostname = "guardian-v07-edge-001"
        csr_pem = generate_csr(temp, hostname)
        key_path = temp / f"{hostname}.key.pem"
        enrolled = gateway_require(
            "POST", "/api/v1/enrollments",
            {
                "token": enrollment_token,
                "platform": "windows",
                "hostname": hostname,
                "agent_version": "0.7.0-e2e",
                "csr_pem": csr_pem,
            },
            expected=(201,),
        )
        device_id = enrolled["device_id"]
        context = make_mtls_context(temp, enrolled, key_path)
        wait_edge_ready(context)

        spoofed_tenant = str(uuid4())
        heartbeat_payload = {
            "session_id": str(uuid4()),
            "agent_version": "0.7.0-e2e",
            "platform": "windows",
            "platform_version": "11-e2e",
            "capabilities": [
                "heartbeat.v1", "telemetry.v1", "inventory.v1",
                "command.inventory_refresh.v1", "command.device_reboot.v1", "command.service_restart.v1",
                "spool.v1", "update.v1",
            ],
            "capability_version": 1,
            "sent_at": iso_now(),
        }
        heartbeat = edge_require(
            context, "POST", "/api/v1/device/heartbeat", heartbeat_payload,
            extra_headers={
                "X-Guardian-Tenant-ID": spoofed_tenant,
                "X-Guardian-Asset-ID": str(uuid4()),
                "X-Guardian-Device-ID": str(uuid4()),
                "X-Guardian-Certificate-Serial": "DEADBEEF",
                "X-Guardian-Proxy-Token": "attacker-controlled",
                "Forwarded": "for=attacker",
                "X-Forwarded-For": "attacker",
            },
        )
        assert heartbeat["device_id"] == device_id, heartbeat
        assert heartbeat["state"] == "online", heartbeat
        wait_for_audit_event(tenant_id, access_token, "device.online", device_id)

        # A valid device certificate never opens an administrative route.
        admin_status, _, _ = http_json(EDGE, "GET", "/api/v1/audit/records", context=context)
        assert admin_status == 404, admin_status

        batch_id = str(uuid4())
        telemetry_payload = {
            "batch_id": batch_id,
            "sent_at": iso_now(),
            "samples": [
                {"metric": "cpu.utilization_pct", "value": 17.5, "labels": {}, "observed_at": iso_now()},
                {"metric": "memory.total_bytes", "value": 8589934592, "labels": {}, "observed_at": iso_now()},
                {"metric": "memory.used_bytes", "value": 3221225472, "labels": {}, "observed_at": iso_now()},
                {"metric": "disk.total_bytes", "value": 256000000000, "labels": {"volume": "C:\\"}, "observed_at": iso_now()},
                {"metric": "disk.free_bytes", "value": 128000000000, "labels": {"volume": "C:\\"}, "observed_at": iso_now()},
            ],
        }
        telemetry_ack = edge_require(context, "POST", "/api/v1/device/telemetry", telemetry_payload)
        duplicate_ack = edge_require(context, "POST", "/api/v1/device/telemetry", telemetry_payload)
        assert telemetry_ack["duplicate"] is False, telemetry_ack
        assert duplicate_ack["duplicate"] is True, duplicate_ack
        assert duplicate_ack["batch_record_id"] == telemetry_ack["batch_record_id"]
        latest = gateway_require("GET", f"/api/v1/telemetry/devices/{device_id}/latest", token=access_token)
        metrics = {sample["metric"] for sample in latest["samples"]}
        assert {"cpu.utilization_pct", "memory.total_bytes", "memory.used_bytes", "disk.total_bytes", "disk.free_bytes"}.issubset(metrics), latest

        command = gateway_require(
            "POST", "/api/v1/commands",
            {
                "tenant_id": tenant_id,
                "device_id": device_id,
                "guardian_asset_id": asset_id,
                "command_type": "inventory.refresh",
                "arguments": {},
                "idempotency_key": f"v07-edge-{uuid4()}",
                "expires_in_seconds": 900,
            },
            access_token, expected=(201,),
        )
        command_id = command["command_id"]
        acquired = edge_require(context, "POST", "/api/v1/device/commands/acquire")
        assert len(acquired) == 1 and acquired[0]["command_id"] == command_id, acquired
        execution_token = acquired[0]["execution_token"]
        edge_require(
            context, "POST", f"/api/v1/device/commands/{command_id}/running",
            {"execution_token": execution_token},
        )
        started = iso_now()
        finished = iso_now()
        result_payload = {
            "execution_token": execution_token,
            "result_sequence": 1,
            "status": "succeeded",
            "exit_code": 0,
            "summary": "v0.7 mTLS command completed",
            "started_at": started,
            "finished_at": finished,
        }
        result = edge_require(context, "POST", f"/api/v1/device/commands/{command_id}/result", result_payload)
        replay = edge_require(context, "POST", f"/api/v1/device/commands/{command_id}/result", result_payload)
        assert replay["result_id"] == result["result_id"], (result, replay)
        command_read = gateway_require("GET", f"/api/v1/commands/{command_id}", token=access_token)
        assert command_read["state"] == "succeeded", command_read
        wait_for_audit_event(tenant_id, access_token, "command.succeeded", command_id)

        # Revoke using PKI management API, then prove the edge refreshes CRL and blocks the certificate.
        revoke_status, revoked, _ = http_json(
            PKI, "POST", f"/api/v1/certificates/{enrolled['certificate_id']}/revoke",
            {"reason": "key_compromise"}, token=access_token,
        )
        assert revoke_status == 200 and revoked["status"] == "revoked", (revoke_status, revoked)
        deadline = time.monotonic() + 75
        blocked: tuple[int, Any, dict[str, str]] | None = None
        while time.monotonic() < deadline:
            blocked = http_json(EDGE, "POST", "/api/v1/device/heartbeat", heartbeat_payload, context=context)
            if blocked[0] == 401:
                break
            time.sleep(2)
        assert blocked is not None and blocked[0] == 401, blocked
        assert blocked[1]["code"] == "device_edge.certificate_revoked", blocked

        inspected = json.loads(
            subprocess.check_output(
                ["docker", "inspect", subprocess.check_output(["docker", "compose", "ps", "-q", "device-edge-service"], text=True).strip()],
                text=True,
            )
        )[0]
        destinations = {mount["Destination"] for mount in inspected["Mounts"]}
        assert "/var/lib/guardian/device-edge-ca" not in destinations, destinations
        assert "/var/lib/guardian/device-edge-tls" in destinations, destinations
        assert str(inspected["Config"].get("User", "")) not in {"", "0", "root", "0:0"}, inspected["Config"].get("User")

        print(json.dumps({
            "status": "ok",
            "tenant_id": tenant_id,
            "asset_id": asset_id,
            "device_id": device_id,
            "command_id": command_id,
            "mtls_identity_certified": True,
            "spoofed_headers_ignored": True,
            "telemetry_certified": True,
            "command_lifecycle_certified": True,
            "result_replay_certified": True,
            "revocation_enforced": True,
            "device_edge_ca_private_key_isolated": True,
            "device_edge_non_root": True,
        }, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
