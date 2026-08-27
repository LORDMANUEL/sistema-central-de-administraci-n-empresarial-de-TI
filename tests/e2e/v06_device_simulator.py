from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class DeviceIdentity:
    tenant_id: str
    guardian_asset_id: str
    device_id: str
    certificate_serial: str


class DeviceRequestError(RuntimeError):
    pass


def http_json(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> tuple[int, Any, dict[str, str]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        method=method,
        headers=request_headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            data: Any
            if not raw:
                data = None
            elif "json" in response.headers.get("Content-Type", ""):
                data = json.loads(raw)
            else:
                data = raw.decode("utf-8", errors="replace")
            return response.status, data, dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            data = None if not raw else json.loads(raw)
        except (TypeError, ValueError):
            data = raw.decode("utf-8", errors="replace")
        return exc.code, data, dict(exc.headers.items())


class DeviceSimulator:
    def __init__(
        self,
        identity: DeviceIdentity,
        proxy_token: str,
        *,
        agent_control_url: str = "http://127.0.0.1:8007",
        command_url: str = "http://127.0.0.1:8008",
        telemetry_url: str = "http://127.0.0.1:8009",
    ) -> None:
        if not proxy_token:
            raise ValueError("proxy_token is required for the v0.6 simulator")
        self.identity = identity
        self.proxy_token = proxy_token
        self.agent_control_url = agent_control_url.rstrip("/")
        self.command_url = command_url.rstrip("/")
        self.telemetry_url = telemetry_url.rstrip("/")
        self.session_id = uuid4()

    def trusted_headers(self) -> dict[str, str]:
        return {
            "X-Guardian-Proxy-Token": self.proxy_token,
            "X-Guardian-Tenant-ID": self.identity.tenant_id,
            "X-Guardian-Asset-ID": self.identity.guardian_asset_id,
            "X-Guardian-Device-ID": self.identity.device_id,
            "X-Guardian-Certificate-Serial": self.identity.certificate_serial,
        }

    def _require(
        self,
        base_url: str,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        expected: tuple[int, ...] = (200,),
        headers: dict[str, str] | None = None,
    ) -> Any:
        merged = self.trusted_headers()
        if headers:
            merged.update(headers)
        status, data, _ = http_json(base_url, method, path, payload, headers=merged)
        if status not in expected:
            raise DeviceRequestError(f"{method} {path} failed: HTTP {status}: {data}")
        return data

    def heartbeat(
        self,
        *,
        capabilities: list[str] | None = None,
        capability_version: int = 1,
        agent_version: str = "0.7.0-simulator",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = {
            "session_id": str(self.session_id),
            "agent_version": agent_version,
            "platform": "windows",
            "platform_version": "10.0.26100",
            "capabilities": capabilities or ["inventory.basic", "command.inventory.refresh"],
            "capability_version": capability_version,
            "sent_at": datetime.now(UTC).isoformat(),
        }
        return self._require(self.agent_control_url, "POST", "/api/v1/device/heartbeat", payload), payload

    def acquire(self, *, limit: int = 10) -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"limit": limit})
        return self._require(
            self.command_url,
            "POST",
            f"/api/v1/device/commands/acquire?{query}",
            {},
        )

    def mark_running(self, command_id: str, execution_token: str) -> dict[str, Any]:
        return self._require(
            self.command_url,
            "POST",
            f"/api/v1/device/commands/{command_id}/running",
            {"execution_token": execution_token},
        )

    def result_payload(
        self,
        execution_token: str,
        *,
        result_sequence: int = 1,
        status: str = "succeeded",
        exit_code: int = 0,
        summary: str = "simulated command completed",
    ) -> dict[str, Any]:
        finished_at = datetime.now(UTC)
        return {
            "execution_token": execution_token,
            "result_sequence": result_sequence,
            "status": status,
            "exit_code": exit_code,
            "summary": summary,
            "started_at": (finished_at - timedelta(seconds=1)).isoformat(),
            "finished_at": finished_at.isoformat(),
        }

    def submit_result(self, command_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._require(
            self.command_url,
            "POST",
            f"/api/v1/device/commands/{command_id}/result",
            payload,
        )

    def submit_telemetry(
        self,
        payload: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        now = datetime.now(UTC)
        batch = payload or {
            "batch_id": str(uuid4()),
            "sent_at": now.isoformat(),
            "samples": [
                {
                    "metric": "cpu.utilization_pct",
                    "value": 31.4,
                    "labels": {},
                    "observed_at": now.isoformat(),
                },
                {
                    "metric": "memory.used_bytes",
                    "value": 2147483648,
                    "labels": {},
                    "observed_at": now.isoformat(),
                },
            ],
        }
        return self._require(self.telemetry_url, "POST", "/api/v1/device/telemetry", batch), batch

    def raw_command_result(
        self,
        command_id: str | UUID,
        payload: dict[str, Any],
    ) -> tuple[int, Any, dict[str, str]]:
        return http_json(
            self.command_url,
            "POST",
            f"/api/v1/device/commands/{command_id}/result",
            payload,
            headers=self.trusted_headers(),
        )
