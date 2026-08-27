from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

IDENTITY = "http://127.0.0.1:8001"
TENANT = "http://127.0.0.1:8002"
AUDIT = "http://127.0.0.1:8006"

ADMIN_EMAIL = "enrollment-ci@example.com"
ADMIN_PASSWORD = "Guardian-Enrollment-CI-2026!"
SECOND_EMAIL = "audit-tenant2@example.com"
SECOND_PASSWORD = "Guardian-Audit-Tenant2-2026!"
SECRET_MARKER = "AUDIT-SMOKE-SECRET-DO-NOT-PERSIST"
CSR_MARKER = "-----BEGIN CERTIFICATE REQUEST-----AUDIT-SMOKE-SECRET-----END CERTIFICATE REQUEST-----"


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
        try:
            data = None if not raw else json.loads(raw)
        except (TypeError, ValueError):
            data = raw.decode("utf-8", errors="replace")
        return exc.code, data


def require(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    expected: tuple[int, ...] = (200,),
) -> Any:
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


def audit_records(tenant_id: str, token: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"tenant_id": tenant_id, "limit": 500})
    result = require("GET", f"{AUDIT}/api/v1/audit/records?{query}", token=token)
    return result["items"]


def verify_chain(tenant_id: str, token: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"tenant_id": tenant_id})
    return require("GET", f"{AUDIT}/api/v1/audit/verify?{query}", token=token)


def wait_for_event(
    tenant_id: str,
    token: str,
    *,
    source_event_id: str | None = None,
    source_type: str | None = None,
    timeout_seconds: int = 120,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    last: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        last = audit_records(tenant_id, token)
        if source_event_id is not None and any(item["source_event_id"] == source_event_id for item in last):
            return last
        if source_type is not None and any(item["source_type"] == source_type for item in last):
            return last
        time.sleep(1)
    raise RuntimeError(
        f"Audit event did not arrive for tenant={tenant_id}; event_id={source_event_id}; type={source_type}; count={len(last)}"
    )


def wait_chain_stable(tenant_id: str, token: str, *, samples: int = 3, timeout_seconds: int = 60) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_sequence: int | None = None
    stable = 0
    last_result: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        result = verify_chain(tenant_id, token)
        assert result["valid"] is True, result
        sequence = int(result["last_sequence"])
        if sequence == last_sequence:
            stable += 1
        else:
            stable = 1
            last_sequence = sequence
        last_result = result
        if stable >= samples:
            return result
        time.sleep(1)
    raise RuntimeError(f"Audit chain did not stabilize: {last_result}")


def publish_duplicate_event(event: dict[str, Any]) -> None:
    encoded = json.dumps(event, separators=(",", ":"), sort_keys=True)
    publisher = f'''import asyncio\nimport json\nimport nats\n\nevent = json.loads({encoded!r})\npayload = json.dumps(event, separators=(",", ":"), sort_keys=True).encode("utf-8")\n\nasync def main():\n    nc = await nats.connect("nats://nats:4222", connect_timeout=5)\n    js = nc.jetstream()\n    await js.publish("guardian.audit.smoke.duplicate", payload)\n    await js.publish("guardian.audit.smoke.duplicate", payload)\n    await nc.drain()\n\nasyncio.run(main())\n'''
    subprocess.run(
        ["docker", "compose", "exec", "-T", "audit-consumer", "python", "-"],
        input=publisher,
        text=True,
        check=True,
    )


def expect_postgres_rejection(sql: str) -> None:
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "guardian",
            "-d",
            "guardian_audit",
            "-c",
            sql,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode == 0:
        raise AssertionError(f"PostgreSQL mutation unexpectedly succeeded: {sql}")
    combined = (completed.stdout + completed.stderr).lower()
    assert "append-only" in combined or "append only" in combined, combined


def main() -> None:
    for endpoint in (
        f"{IDENTITY}/health/ready",
        f"{TENANT}/health/ready",
        f"{AUDIT}/health/ready",
    ):
        wait_ready(endpoint)

    login = require(
        "POST",
        f"{IDENTITY}/api/v1/auth/login",
        {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    admin_token = login["access_token"]

    tenants = require("GET", f"{TENANT}/api/v1/tenants", token=admin_token)
    primary = next(item for item in tenants if item["slug"] == "enrollment-ci-company")
    tenant_id = primary["id"]

    records = wait_for_event(tenant_id, admin_token, source_type="device.enrolled")
    assert records, "Audit did not persist tenant events"
    chain = wait_chain_stable(tenant_id, admin_token)
    assert chain["record_count"] >= 1, chain

    baseline_sequence = int(chain["last_sequence"])
    duplicate_event_id = str(uuid4())
    duplicate_event = {
        "schema_version": 1,
        "event_id": duplicate_event_id,
        "type": "audit.smoke.duplicate",
        "aggregate_type": "asset",
        "aggregate_id": str(uuid4()),
        "occurred_at": datetime.now(UTC).isoformat(),
        "data": {
            "tenant_id": tenant_id,
            "hostname": "audit-smoke-host",
            "actor_type": "system",
            "action": "audit.smoke.duplicate",
            "outcome": "success",
            "request_id": f"audit-smoke-{duplicate_event_id}",
            "password": SECRET_MARKER,
            "authorization": f"Bearer {SECRET_MARKER}",
            "enrollment_token": f"gdt_{SECRET_MARKER}",
            "csr_pem": CSR_MARKER,
            "private_key": SECRET_MARKER,
        },
    }
    publish_duplicate_event(duplicate_event)

    records = wait_for_event(tenant_id, admin_token, source_event_id=duplicate_event_id)
    final_chain = wait_chain_stable(tenant_id, admin_token)
    matching = [item for item in records if item["source_event_id"] == duplicate_event_id]
    assert len(matching) == 1, matching
    assert int(final_chain["last_sequence"]) == baseline_sequence + 1, (chain, final_chain)
    duplicate_record = matching[0]

    serialized = json.dumps(audit_records(tenant_id, admin_token), sort_keys=True)
    for forbidden in (
        SECRET_MARKER,
        CSR_MARKER,
        "-----BEGIN CERTIFICATE REQUEST-----",
        ADMIN_PASSWORD,
        "gdt_AUDIT-SMOKE-SECRET-DO-NOT-PERSIST",
    ):
        assert forbidden not in serialized, forbidden

    created_user = require(
        "POST",
        f"{IDENTITY}/api/v1/users",
        {
            "email": SECOND_EMAIL,
            "display_name": "Audit Tenant Two Reader",
            "role": "viewer",
            "password": SECOND_PASSWORD,
        },
        admin_token,
        expected=(201,),
    )
    second_login = require(
        "POST",
        f"{IDENTITY}/api/v1/auth/login",
        {"email": SECOND_EMAIL, "password": SECOND_PASSWORD},
    )
    second_token = second_login["access_token"]

    second_tenant = require(
        "POST",
        f"{TENANT}/api/v1/tenants",
        {
            "name": "Audit CI Tenant Two",
            "slug": "audit-ci-tenant-two",
            "timezone": "America/Tegucigalpa",
            "locale": "es-HN",
        },
        admin_token,
        expected=(201,),
    )
    second_tenant_id = second_tenant["id"]
    require(
        "POST",
        f"{TENANT}/api/v1/tenants/{second_tenant_id}/memberships",
        {"user_id": created_user["id"], "role": "auditor"},
        admin_token,
        expected=(201,),
    )
    wait_for_event(second_tenant_id, admin_token, source_type="tenant.created")

    second_query = urllib.parse.urlencode({"tenant_id": second_tenant_id, "limit": 20})
    allowed_status, allowed = request(
        "GET",
        f"{AUDIT}/api/v1/audit/records?{second_query}",
        token=second_token,
    )
    assert allowed_status == 200 and allowed["items"], (allowed_status, allowed)

    primary_query = urllib.parse.urlencode({"tenant_id": tenant_id, "limit": 20})
    denied_status, denied = request(
        "GET",
        f"{AUDIT}/api/v1/audit/records?{primary_query}",
        token=second_token,
    )
    assert denied_status == 403, (denied_status, denied)
    assert denied["error"]["code"] == "audit.access_denied", denied

    detail_status, detail_denied = request(
        "GET",
        f"{AUDIT}/api/v1/audit/records/{duplicate_record['id']}",
        token=second_token,
    )
    assert detail_status == 403, (detail_status, detail_denied)

    record_id = duplicate_record["id"]
    expect_postgres_rejection(
        f"UPDATE audit_records SET outcome='failure' WHERE id='{record_id}'"
    )
    expect_postgres_rejection(
        f"DELETE FROM audit_records WHERE id='{record_id}'"
    )
    after = require(
        "GET",
        f"{AUDIT}/api/v1/audit/records/{record_id}",
        token=admin_token,
    )
    assert after["outcome"] == "success", after

    print(
        json.dumps(
            {
                "status": "ok",
                "tenant_id": tenant_id,
                "second_tenant_id": second_tenant_id,
                "audit_record_count": final_chain["record_count"],
                "duplicate_event_id": duplicate_event_id,
                "duplicate_sequence": duplicate_record["sequence"],
                "chain_valid": final_chain["valid"],
                "cross_tenant_denied": True,
                "append_only_verified": True,
                "secret_scan_verified": True,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
