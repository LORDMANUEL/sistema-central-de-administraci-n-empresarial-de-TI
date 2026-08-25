from __future__ import annotations

from dataclasses import dataclass

import httpx

from .errors import GuardianError


@dataclass(frozen=True)
class AssetReference:
    asset_id: str
    tenant_id: str
    status: str
    asset_type: str | None = None
    display_name: str | None = None


class AssetClient:
    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get(self, asset_id: str, bearer_token: str) -> AssetReference:
        try:
            response = httpx.get(
                f"{self.base_url}/api/v1/assets/{asset_id}",
                headers={"Authorization": f"Bearer {bearer_token}"},
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise GuardianError(503, "enrollment.asset_service_unavailable", "Asset Service is unavailable") from exc

        if response.status_code == 404:
            raise GuardianError(404, "enrollment.asset_not_found", "Asset not found")
        if response.status_code == 403:
            raise GuardianError(403, "enrollment.access_denied", "You do not have access to this asset")
        if response.status_code >= 500:
            raise GuardianError(503, "enrollment.asset_service_unavailable", "Asset Service is unavailable")
        try:
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GuardianError(503, "enrollment.asset_service_invalid_response", "Asset Service response is invalid") from exc

        asset_id_value = data.get("guardian_asset_id")
        tenant_id = data.get("tenant_id")
        status = data.get("status")
        if not isinstance(asset_id_value, str) or not isinstance(tenant_id, str) or not isinstance(status, str):
            raise GuardianError(503, "enrollment.asset_service_invalid_response", "Asset Service response is invalid")

        return AssetReference(
            asset_id=asset_id_value,
            tenant_id=tenant_id,
            status=status,
            asset_type=data.get("asset_type") if isinstance(data.get("asset_type"), str) else None,
            display_name=data.get("display_name") if isinstance(data.get("display_name"), str) else None,
        )


def validate_asset_tenant(asset: AssetReference, tenant_id: str) -> None:
    if asset.tenant_id != tenant_id:
        raise GuardianError(
            422,
            "enrollment.asset_tenant_mismatch",
            "Asset does not belong to the requested tenant",
        )
