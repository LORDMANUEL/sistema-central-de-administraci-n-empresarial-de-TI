from __future__ import annotations

import argparse
import json
import ssl
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from gateway_audit_smoke import generate_csr, require as gateway_require, wait_ready as wait_gateway_ready
from v07_device_edge_smoke import edge_require, http_json, wait_edge_ready

EDGE = "https://localhost:8443"


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


def build_context(runtime: Path) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(runtime / "device-edge-server-ca.pem"))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=str(runtime / "device-client-chain.pem"), keyfile=str(runtime / "guardian-v08-ui.key.pem"))
    return context


def prepare(runtime: Path) -> dict[str, Any]:
    runtime.mkdir(parents=True, exist_ok=True)
    for child in runtime.iterdir():
        if child.is_file():
            child.unlink()

    wait_gateway_ready()
    email = "v08-console-ci@example.com"
    password = "Guardian-v08-Console-CI-2026!"
    gateway_require(
        "POST",
        "/api/v1/auth/bootstrap",
        {"email": email, "display_name": "v0.8 Console CI", "password": password},
        expected=(201,),
    )
    access = gateway_require("POST", "/api/v1/auth/login", {"email": email, "password": password})["access_token"]

    tenant = gateway_require(
        "POST",
        "/api/v1/tenants",
        {"name": "Guardian v08 Console", "slug": "guardian-v08-console", "timezone": "America/Tegucigalpa", "locale": "es-HN"},
        access,
        expected=(201,),
    )
    tenant_id = tenant["id"]
    site = gateway_require(
        "POST", f"/api/v1/tenants/{tenant_id}/sites",
        {"code": "SPS", "name": "San Pedro Sula"}, access, expected=(201,),
    )
    department = gateway_require(
        "POST", f"/api/v1/tenants/{tenant_id}/departments",
        {"code": "IT", "name": "Tecnologia"}, access, expected=(201,),
    )
    asset = gateway_require(
        "POST", "/api/v1/assets",
        {
            "tenant_id": tenant_id,
            "site_id": site["id"],
            "department_id": department["id"],
            "asset_type": "computer",
            "display_name": "v0.8 Browser Endpoint",
            "hostname": "guardian-v08-ui",
            "serial_number": "GUARDIAN-V08-UI-001",
        }, access, expected=(201,),
    )
    asset_id = asset["guardian_asset_id"]
    enrollment_token = gateway_require(
        "POST", "/api/v1/enrollment-tokens",
        {"tenant_id": tenant_id, "asset_id": asset_id, "expires_in_minutes": 60}, access, expected=(201,),
    )["token"]

    csr_pem = generate_csr(runtime, "guardian-v08-ui")
    enrolled = gateway_require(
        "POST", "/api/v1/enrollments",
        {
            "token": enrollment_token,
            "platform": "windows",
            "hostname": "guardian-v08-ui",
            "agent_version": "0.8.0-e2e",
            "csr_pem": csr_pem,
        }, expected=(201,),
    )
    device_id = enrolled["device_id"]

    subprocess.run(
        ["docker", "compose", "cp", "device-edge-service:/var/lib/guardian/device-edge-tls/server-ca.pem", str(runtime / "device-edge-server-ca.pem")],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    (runtime / "device-client-chain.pem").write_text(enrolled["certificate_pem"] + enrolled["ca_chain_pem"], encoding="utf-8")
    context = build_context(runtime)
    wait_edge_ready(context)

    heartbeat = edge_require(context, "POST", "/api/v1/device/heartbeat", {
        "session_id": str(uuid4()),
        "agent_version": "0.8.0-e2e",
        "platform": "windows",
        "platform_version": "11-24H2-e2e",
        "capabilities": [
            "heartbeat.v1", "telemetry.v1", "inventory.v1",
            "command.inventory_refresh.v1", "command.device_reboot.v1", "command.service_restart.v1",
            "spool.v1", "update.v1",
        ],
        "capability_version": 1,
        "sent_at": iso_now(),
    })
    assert heartbeat["device_id"] == device_id and heartbeat["state"] == "online", heartbeat

    telemetry = edge_require(context, "POST", "/api/v1/device/telemetry", {
        "batch_id": str(uuid4()),
        "sent_at": iso_now(),
        "samples": [
            {"metric": "cpu.utilization_pct", "value": 17.5, "labels": {}, "observed_at": iso_now()},
            {"metric": "memory.total_bytes", "value": 8589934592, "labels": {}, "observed_at": iso_now()},
            {"metric": "memory.used_bytes", "value": 3221225472, "labels": {}, "observed_at": iso_now()},
            {"metric": "disk.total_bytes", "value": 256000000000, "labels": {"volume": "C:\\"}, "observed_at": iso_now()},
            {"metric": "disk.free_bytes", "value": 128000000000, "labels": {"volume": "C:\\"}, "observed_at": iso_now()},
            {"metric": "network.rx_bytes_total", "value": 1048576, "labels": {}, "observed_at": iso_now()},
            {"metric": "network.tx_bytes_total", "value": 524288, "labels": {}, "observed_at": iso_now()},
        ],
    })
    assert telemetry["accepted_samples"] == 7, telemetry

    fixture = {
        "email": email,
        "password": password,
        "tenant_id": tenant_id,
        "tenant_name": tenant["name"],
        "site_id": site["id"],
        "site_name": site["name"],
        "asset_id": asset_id,
        "asset_name": asset["display_name"],
        "device_id": device_id,
    }
    (runtime / "fixture.json").write_text(json.dumps(fixture, sort_keys=True), encoding="utf-8")
    return fixture


def agent_loop(runtime: Path, timeout_seconds: int) -> dict[str, Any]:
    fixture = json.loads((runtime / "fixture.json").read_text(encoding="utf-8"))
    context = build_context(runtime)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status, acquired, _ = http_json(EDGE, "POST", "/api/v1/device/commands/acquire", context=context, timeout=10)
        if status == 200 and acquired:
            command = acquired[0]
            if command["command_type"] != "inventory.refresh":
                raise RuntimeError(f"unexpected command in v0.8 browser E2E: {command}")
            command_id = command["command_id"]
            execution_token = command["execution_token"]
            edge_require(context, "POST", f"/api/v1/device/commands/{command_id}/running", {"execution_token": execution_token})
            started = iso_now()
            result = edge_require(context, "POST", f"/api/v1/device/commands/{command_id}/result", {
                "execution_token": execution_token,
                "result_sequence": 1,
                "status": "succeeded",
                "exit_code": 0,
                "summary": "v0.8 browser E2E inventory refresh completed",
                "started_at": started,
                "finished_at": iso_now(),
            })
            output = {"status": "ok", "device_id": fixture["device_id"], "command_id": command_id, "result_id": result["result_id"]}
            (runtime / "agent-result.json").write_text(json.dumps(output, sort_keys=True), encoding="utf-8")
            return output
        if status not in {200, 204}:
            raise RuntimeError(f"command acquire failed HTTP {status}: {acquired}")
        time.sleep(1)
    raise RuntimeError("timed out waiting for browser-created command")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "agent-loop"))
    parser.add_argument("runtime", type=Path)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    result = prepare(args.runtime) if args.mode == "prepare" else agent_loop(args.runtime, args.timeout)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"v0.8 fixture failed: {exc}", file=sys.stderr)
        raise
