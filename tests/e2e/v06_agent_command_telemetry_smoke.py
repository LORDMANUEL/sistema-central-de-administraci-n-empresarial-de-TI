from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any
from uuid import uuid4

from gateway_audit_smoke import (
    audit_records,
    generate_csr,
    request as gateway_request,
    require as gateway_require,
    wait_ready as wait_gateway_ready,
)
from v06_device_simulator import DeviceIdentity, DeviceSimulator, http_json


DEVICE_PROXY_SHARED_SECRET = os.environ.get("DEVICE_PROXY_SHARED_SECRET", "")


def wait_service_ready(base_url: str, timeout_seconds: int = 240) -> None:
    deadline = time.monotonic() + timeout_seconds
    last: tuple[int, Any, dict[str, str]] | None = None
    while time.monotonic() < deadline:
        try:
            last = http_json(base_url, "GET", "/health/ready", timeout=5)
            if last[0] == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(f"Service did not become ready: {base_url}; last={last}")


def records_for(records: list[dict[str, Any]], source_type: str, resource_id: str) -> list[dict[str, Any]]:
    return [
        item
        for item in records
        if item.get("source_type") == source_type and item.get("resource_id") == resource_id
    ]


def wait_for_audit_event(
    tenant_id: str,
    access_token: str,
    source_type: str,
    resource_id: str,
    *,
    minimum_count: int = 1,
    timeout_seconds: int = 120,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout_seconds
    last: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        last = audit_records(tenant_id, access_token)
        matching = records_for(last, source_type, resource_id)
        if len(matching) >= minimum_count:
            return matching, last
        time.sleep(1)
    raise RuntimeError(
        f"Audit event did not arrive: type={source_type}, resource_id={resource_id}, "
        f"minimum_count={minimum_count}, records={len(last)}"
    )


def postgres_scalar(database: str, sql: str) -> str:
    user = os.environ.get("POSTGRES_USER", "guardian")
    output = subprocess.check_output(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            user,
            "-d",
            database,
            "-tAc",
            sql,
        ],
        text=True,
    )
    return output.strip()


def wait_pending_outbox_clear(
    database: str,
    event_type: str,
    *,
    timeout_seconds: int = 120,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last = "unknown"
    while time.monotonic() < deadline:
        last = postgres_scalar(
            database,
            "SELECT count(*) FROM outbox_events "
            f"WHERE event_type='{event_type}' AND published_at IS NULL;",
        )
        if last == "0":
            return
        time.sleep(1)
    raise RuntimeError(f"Pending outbox did not drain: database={database}, event_type={event_type}, count={last}")


def main() -> None:
    if not DEVICE_PROXY_SHARED_SECRET:
        raise RuntimeError("DEVICE_PROXY_SHARED_SECRET must be set for v0.6 certification")

    wait_gateway_ready()
    for url in (
        "http://127.0.0.1:8007",
        "http://127.0.0.1:8008",
        "http://127.0.0.1:8009",
    ):
        wait_service_ready(url)

    email = "v06-core-ci@example.com"
    password = "Guardian-v06-Core-CI-2026!"
    gateway_require(
        "POST",
        "/api/v1/auth/bootstrap",
        {"email": email, "display_name": "v0.6 Core CI", "password": password},
        expected=(201,),
    )
    login = gateway_require(
        "POST",
        "/api/v1/auth/login",
        {"email": email, "password": password},
    )
    access_token = login["access_token"]

    tenant = gateway_require(
        "POST",
        "/api/v1/tenants",
        {
            "name": "Guardian v06 CI",
            "slug": "guardian-v06-ci",
            "timezone": "America/Tegucigalpa",
            "locale": "es-HN",
        },
        access_token,
        expected=(201,),
    )
    tenant_id = tenant["id"]
    site = gateway_require(
        "POST",
        f"/api/v1/tenants/{tenant_id}/sites",
        {"code": "SPS", "name": "San Pedro Sula"},
        access_token,
        expected=(201,),
    )
    department = gateway_require(
        "POST",
        f"/api/v1/tenants/{tenant_id}/departments",
        {"code": "IT", "name": "Tecnologia"},
        access_token,
        expected=(201,),
    )
    asset = gateway_require(
        "POST",
        "/api/v1/assets",
        {
            "tenant_id": tenant_id,
            "site_id": site["id"],
            "department_id": department["id"],
            "asset_type": "computer",
            "display_name": "v0.6 Device Simulator",
            "hostname": "guardian-v06-sim-001",
            "serial_number": "GUARDIAN-V06-SIM-001",
        },
        access_token,
        expected=(201,),
    )
    asset_id = asset["guardian_asset_id"]

    enrollment_token_result = gateway_require(
        "POST",
        "/api/v1/enrollment-tokens",
        {"tenant_id": tenant_id, "asset_id": asset_id, "expires_in_minutes": 60},
        access_token,
        expected=(201,),
    )
    enrollment_token = enrollment_token_result["token"]
    with tempfile.TemporaryDirectory(prefix="guardian-v06-core-") as temp:
        csr = generate_csr(Path(temp), "guardian-v06-sim-001")
        enrolled = gateway_require(
            "POST",
            "/api/v1/enrollments",
            {
                "token": enrollment_token,
                "platform": "windows",
                "hostname": "GUARDIAN-V06-SIM-001",
                "agent_version": "0.7.0-simulator",
                "csr_pem": csr,
            },
            expected=(201,),
        )

    device_id = enrolled["device_id"]
    simulator = DeviceSimulator(
        DeviceIdentity(
            tenant_id=tenant_id,
            guardian_asset_id=asset_id,
            device_id=device_id,
            certificate_serial=enrolled["certificate_serial_hex"],
        ),
        DEVICE_PROXY_SHARED_SECRET,
    )

    heartbeat, heartbeat_payload = simulator.heartbeat(
        capabilities=["inventory.basic", "command.reboot", "command.service.restart"],
        capability_version=1,
    )
    assert heartbeat["device_id"] == device_id, heartbeat
    assert heartbeat["state"] == "online", heartbeat
    online_events, _ = wait_for_audit_event(tenant_id, access_token, "device.online", device_id)
    assert len(online_events) == 1, online_events
    assert online_events[0]["resource_type"] == "device", online_events[0]

    # Device endpoints are not bearer-admin Gateway routes, even with spoofable headers.
    status, blocked, _ = gateway_request(
        "POST",
        "/api/v1/device/heartbeat",
        heartbeat_payload,
        access_token,
        extra_headers=simulator.trusted_headers(),
    )
    assert status == 404, (status, blocked)
    assert blocked["error"]["code"] == "gateway.route_not_allowed", blocked

    command = gateway_require(
        "POST",
        "/api/v1/commands",
        {
            "tenant_id": tenant_id,
            "device_id": device_id,
            "guardian_asset_id": asset_id,
            "command_type": "inventory.refresh",
            "arguments": {},
            "idempotency_key": f"v06-ci-{uuid4()}",
            "expires_in_seconds": 900,
        },
        access_token,
        expected=(201,),
    )
    command_id = command["command_id"]

    acquired = simulator.acquire()
    assert len(acquired) == 1, acquired
    assert acquired[0]["command_id"] == command_id, acquired
    assert acquired[0]["command_type"] == "inventory.refresh", acquired[0]
    execution_token = acquired[0]["execution_token"]
    simulator.mark_running(command_id, execution_token)

    result_payload = simulator.result_payload(
        execution_token,
        summary="inventory refresh completed by deterministic simulator",
    )
    result = simulator.submit_result(command_id, result_payload)
    duplicate_result = simulator.submit_result(command_id, result_payload)
    assert duplicate_result["result_id"] == result["result_id"], (result, duplicate_result)

    command_read = gateway_require("GET", f"/api/v1/commands/{command_id}", token=access_token)
    assert command_read["state"] == "succeeded", command_read
    succeeded_events, _ = wait_for_audit_event(tenant_id, access_token, "command.succeeded", command_id)
    assert len(succeeded_events) == 1, succeeded_events
    time.sleep(2)
    after_result_replay = audit_records(tenant_id, access_token)
    assert len(records_for(after_result_replay, "command.succeeded", command_id)) == 1

    # A different normalized device principal cannot reuse the valid execution token/result.
    attacker = DeviceSimulator(
        DeviceIdentity(
            tenant_id=tenant_id,
            guardian_asset_id=asset_id,
            device_id=str(uuid4()),
            certificate_serial=enrolled["certificate_serial_hex"],
        ),
        DEVICE_PROXY_SHARED_SECRET,
    )
    attack_status, attack_body, _ = attacker.raw_command_result(command_id, result_payload)
    assert attack_status == 403, (attack_status, attack_body)
    assert attack_body["error"]["code"] == "command.device_mismatch", attack_body

    telemetry_ack, telemetry_payload = simulator.submit_telemetry()
    duplicate_telemetry_ack, _ = simulator.submit_telemetry(telemetry_payload)
    assert telemetry_ack["duplicate"] is False, telemetry_ack
    assert duplicate_telemetry_ack["duplicate"] is True, duplicate_telemetry_ack
    assert duplicate_telemetry_ack["batch_record_id"] == telemetry_ack["batch_record_id"]

    latest = gateway_require(
        "GET",
        f"/api/v1/telemetry/devices/{device_id}/latest",
        token=access_token,
    )
    metrics = {sample["metric"] for sample in latest["samples"]}
    assert {"cpu.utilization_pct", "memory.used_bytes"}.issubset(metrics), latest
    telemetry_resource_id = telemetry_ack["batch_record_id"]
    telemetry_events, _ = wait_for_audit_event(
        tenant_id,
        access_token,
        "telemetry.batch.accepted",
        telemetry_resource_id,
    )
    assert len(telemetry_events) == 1, telemetry_events
    time.sleep(2)
    after_telemetry_replay = audit_records(tenant_id, access_token)
    assert len(records_for(after_telemetry_replay, "telemetry.batch.accepted", telemetry_resource_id)) == 1

    # Safe domain mutation must persist during NATS outage and publish after recovery.
    before_outage_records = audit_records(tenant_id, access_token)
    capability_events_before = len(records_for(before_outage_records, "device.capabilities.changed", device_id))
    subprocess.run(["docker", "compose", "stop", "nats"], check=True)
    try:
        changed_heartbeat, _ = simulator.heartbeat(
            capabilities=[
                "inventory.basic",
                "command.reboot",
                "command.service.restart",
                "inventory.software",
            ],
            capability_version=2,
        )
        assert changed_heartbeat["state"] == "online", changed_heartbeat
        pending = int(
            postgres_scalar(
                "guardian_agent_control",
                "SELECT count(*) FROM outbox_events "
                "WHERE event_type='device.capabilities.changed' AND published_at IS NULL;",
            )
        )
        assert pending >= 1, pending
    finally:
        subprocess.run(["docker", "compose", "start", "nats"], check=True)

    wait_for_audit_event(
        tenant_id,
        access_token,
        "device.capabilities.changed",
        device_id,
        minimum_count=capability_events_before + 1,
    )
    wait_pending_outbox_clear("guardian_agent_control", "device.capabilities.changed")

    final_records = audit_records(tenant_id, access_token)
    serialized = json.dumps(final_records, sort_keys=True)
    for secret in (
        DEVICE_PROXY_SHARED_SECRET,
        enrollment_token,
        execution_token,
        enrolled["certificate_pem"],
    ):
        assert secret not in serialized

    verify_query = urllib.parse.urlencode({"tenant_id": tenant_id})
    chain = gateway_require("GET", f"/api/v1/audit/verify?{verify_query}", token=access_token)
    assert chain["valid"] is True, chain

    print(
        json.dumps(
            {
                "status": "ok",
                "tenant_id": tenant_id,
                "asset_id": asset_id,
                "device_id": device_id,
                "command_id": command_id,
                "telemetry_batch_record_id": telemetry_resource_id,
                "heartbeat_certified": True,
                "command_lifecycle_certified": True,
                "result_replay_certified": True,
                "telemetry_dedupe_certified": True,
                "device_gateway_boundary_certified": True,
                "cross_device_result_blocked": True,
                "nats_recovery_certified": True,
                "audit_chain_valid": True,
                "audit_secret_safe": True,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
