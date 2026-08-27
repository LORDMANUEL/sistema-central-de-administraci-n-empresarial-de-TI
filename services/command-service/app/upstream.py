from uuid import UUID
import httpx
from .errors import GuardianError

class CoreValidator:
    def __init__(self,settings): self.settings=settings
    def validate_target(self,asset_id:UUID,device_id:UUID,bearer_token:str):
        try:
            asset=httpx.get(f"{self.settings.asset_service_url}/api/v1/assets/{asset_id}",headers={"Authorization":f"Bearer {bearer_token}"},timeout=5)
        except httpx.HTTPError as exc: raise GuardianError(503,"command.asset_unavailable","Asset service unavailable") from exc
        if asset.status_code in {403,404}: raise GuardianError(asset.status_code,"command.target_not_accessible","Command target is not accessible")
        if asset.status_code>=500: raise GuardianError(503,"command.asset_unavailable","Asset service unavailable")
        try: asset.raise_for_status(); ad=asset.json(); tenant_id=UUID(ad["tenant_id"])
        except Exception as exc: raise GuardianError(503,"command.asset_invalid_response","Asset response invalid") from exc
        try:
            device=httpx.get(f"{self.settings.agent_control_service_url}/internal/v1/devices/{device_id}",headers={"X-Guardian-Internal-Token":self.settings.trusted_proxy_token},timeout=5)
        except httpx.HTTPError as exc: raise GuardianError(503,"command.agent_control_unavailable","Agent Control unavailable") from exc
        if device.status_code==404: raise GuardianError(404,"command.device_not_found","Device not found")
        if device.status_code>=400: raise GuardianError(503,"command.agent_control_unavailable","Agent Control unavailable")
        dd=device.json()
        if dd.get("tenant_id")!=str(tenant_id) or dd.get("guardian_asset_id")!=str(asset_id): raise GuardianError(409,"command.device_binding_conflict","Device is not bound to requested asset")
        return tenant_id
