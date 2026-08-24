from __future__ import annotations

import httpx

from .errors import GuardianError
from .tenant_access import TenantAccessDecision


class TenantAccessClient:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def resolve(self, tenant_id: str, user_id: str, bearer_token: str) -> TenantAccessDecision:
        try:
            response = httpx.get(
                f"{self.base_url}/api/v1/tenants/{tenant_id}/access",
                headers={"Authorization": f"Bearer {bearer_token}"},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise GuardianError(503, "asset.tenant_service_unavailable", "Tenant authorization service is unavailable") from exc

        if response.status_code == 403:
            return TenantAccessDecision(allowed=False, role=None, tenant_status="active")
        if response.status_code == 404:
            raise GuardianError(404, "asset.tenant_not_found", "Tenant not found")
        if response.status_code >= 500:
            raise GuardianError(503, "asset.tenant_service_unavailable", "Tenant authorization service is unavailable")
        try:
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GuardianError(503, "asset.tenant_service_invalid_response", "Tenant authorization response is invalid") from exc

        return TenantAccessDecision(
            allowed=bool(data.get("allowed")),
            role=data.get("role"),
            tenant_status=str(data.get("tenant_status", "unknown")),
        )
