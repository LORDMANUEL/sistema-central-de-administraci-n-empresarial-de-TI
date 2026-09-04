from uuid import UUID

import httpx

from .errors import GuardianError


class TenantAccess:
    def __init__(self, settings):
        self.settings = settings

    def _request(self, path: str, bearer_token: str):
        try:
            response = httpx.get(
                f"{self.settings.tenant_service_url}{path}",
                headers={"Authorization": f"Bearer {bearer_token}"},
                timeout=5,
            )
        except httpx.HTTPError as exc:
            raise GuardianError(503, "agent_control.tenant_unavailable", "Tenant service is unavailable") from exc
        if response.status_code in {401, 403, 404}:
            messages = {401: "Authentication failed", 403: "Tenant access denied", 404: "Tenant not found"}
            raise GuardianError(
                response.status_code,
                "agent_control.tenant_access_denied",
                messages[response.status_code],
            )
        if response.status_code >= 400:
            raise GuardianError(503, "agent_control.tenant_unavailable", "Tenant service is unavailable")
        return response

    def accessible_tenant_ids(self, bearer_token: str) -> set[UUID]:
        try:
            data = self._request("/api/v1/tenants", bearer_token).json()
            return {UUID(str(item["id"])) for item in data}
        except GuardianError:
            raise
        except Exception as exc:
            raise GuardianError(503, "agent_control.tenant_invalid_response", "Tenant response is invalid") from exc

    def require_tenant(self, tenant_id: UUID, bearer_token: str) -> None:
        self._request(f"/api/v1/tenants/{tenant_id}", bearer_token)
