from __future__ import annotations

from dataclasses import dataclass
import json as jsonlib

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..authenticated import gateway_request
from ..errors import ConsoleError


@dataclass(frozen=True)
class Operation:
    name: str
    method: str
    console_path: str
    gateway_path: str


OPERATIONS = (
    Operation("users.create", "POST", "/users", "/api/v1/users"),
    Operation("users.list", "GET", "/users", "/api/v1/users"),
    Operation("users.status", "PATCH", "/users/{user_id}/status", "/api/v1/users/{user_id}/status"),
    Operation("tenants.create", "POST", "/tenants", "/api/v1/tenants"),
    Operation("tenants.list", "GET", "/tenants", "/api/v1/tenants"),
    Operation("tenants.get", "GET", "/tenants/{tenant_id}", "/api/v1/tenants/{tenant_id}"),
    Operation("tenants.update", "PATCH", "/tenants/{tenant_id}", "/api/v1/tenants/{tenant_id}"),
    Operation("memberships.upsert", "POST", "/tenants/{tenant_id}/memberships", "/api/v1/tenants/{tenant_id}/memberships"),
    Operation("memberships.list", "GET", "/tenants/{tenant_id}/memberships", "/api/v1/tenants/{tenant_id}/memberships"),
    Operation("memberships.update", "PATCH", "/tenants/{tenant_id}/memberships/{user_id}", "/api/v1/tenants/{tenant_id}/memberships/{user_id}"),
    Operation("sites.create", "POST", "/tenants/{tenant_id}/sites", "/api/v1/tenants/{tenant_id}/sites"),
    Operation("sites.list", "GET", "/tenants/{tenant_id}/sites", "/api/v1/tenants/{tenant_id}/sites"),
    Operation("sites.update", "PATCH", "/tenants/{tenant_id}/sites/{site_id}", "/api/v1/tenants/{tenant_id}/sites/{site_id}"),
    Operation("departments.create", "POST", "/tenants/{tenant_id}/departments", "/api/v1/tenants/{tenant_id}/departments"),
    Operation("departments.list", "GET", "/tenants/{tenant_id}/departments", "/api/v1/tenants/{tenant_id}/departments"),
    Operation("departments.update", "PATCH", "/tenants/{tenant_id}/departments/{department_id}", "/api/v1/tenants/{tenant_id}/departments/{department_id}"),
    Operation("assets.create", "POST", "/assets", "/api/v1/assets"),
    Operation("assets.list", "GET", "/assets", "/api/v1/assets"),
    Operation("assets.get", "GET", "/assets/{asset_id}", "/api/v1/assets/{asset_id}"),
    Operation("assets.external_identity", "POST", "/assets/{asset_id}/external-identities", "/api/v1/assets/{asset_id}/external-identities"),
    Operation("tokens.create", "POST", "/enrollment-tokens", "/api/v1/enrollment-tokens"),
    Operation("tokens.list", "GET", "/enrollment-tokens", "/api/v1/enrollment-tokens"),
    Operation("tokens.revoke", "POST", "/enrollment-tokens/{token_id}/revoke", "/api/v1/enrollment-tokens/{token_id}/revoke"),
    Operation("enrollments.list", "GET", "/enrollments", "/api/v1/enrollments"),
    Operation("enrollments.get", "GET", "/enrollments/{device_id}", "/api/v1/enrollments/{device_id}"),
    Operation("audit.list", "GET", "/audit/records", "/api/v1/audit/records"),
    Operation("audit.get", "GET", "/audit/records/{record_id}", "/api/v1/audit/records/{record_id}"),
    Operation("audit.verify", "GET", "/audit/verify", "/api/v1/audit/verify"),
    Operation("devices.list", "GET", "/devices", "/api/v1/devices"),
    Operation("devices.get", "GET", "/devices/{device_id}", "/api/v1/devices/{device_id}"),
    Operation("commands.create", "POST", "/commands", "/api/v1/commands"),
    Operation("commands.list", "GET", "/commands", "/api/v1/commands"),
    Operation("commands.get", "GET", "/commands/{command_id}", "/api/v1/commands/{command_id}"),
    Operation("commands.cancel", "POST", "/commands/{command_id}/cancel", "/api/v1/commands/{command_id}/cancel"),
    Operation("telemetry.latest", "GET", "/telemetry/devices/{device_id}/latest", "/api/v1/telemetry/devices/{device_id}/latest"),
)

if len({(operation.method, operation.console_path) for operation in OPERATIONS}) != len(OPERATIONS):
    raise RuntimeError("duplicate console operation")
if any("/device/" in operation.gateway_path for operation in OPERATIONS):
    raise RuntimeError("device plane must never be registered in Web Console")

router = APIRouter(prefix="/console/api", tags=["resources"])


def _register(operation: Operation) -> None:
    async def endpoint(request: Request):
        payload = None
        if operation.method in {"POST", "PATCH", "PUT"}:
            raw = await request.body()
            if raw:
                try:
                    payload = jsonlib.loads(raw)
                except Exception as exc:
                    raise ConsoleError(400, "console.invalid_json", "Request body must be valid JSON") from exc
        path = operation.gateway_path.format(**request.path_params)
        response = gateway_request(
            request,
            operation.method,
            path,
            json=payload,
            params=list(request.query_params.multi_items()),
        )
        try:
            data = response.json() if response.content else None
        except Exception as exc:
            raise ConsoleError(502, "console.invalid_gateway_response", "Gateway returned invalid JSON") from exc
        if response.status_code >= 400:
            message = (
                data.get("error", {}).get("message", "Gateway request failed")
                if isinstance(data, dict)
                else "Gateway request failed"
            )
            code = (
                data.get("error", {}).get("code", "console.gateway_request_failed")
                if isinstance(data, dict)
                else "console.gateway_request_failed"
            )
            raise ConsoleError(response.status_code, str(code), str(message))
        return JSONResponse(status_code=response.status_code, content=data)

    endpoint.__name__ = f"console_{operation.name.replace('.', '_')}"
    router.add_api_route(
        operation.console_path,
        endpoint,
        methods=[operation.method],
        name=operation.name,
    )


for _operation in OPERATIONS:
    _register(_operation)
