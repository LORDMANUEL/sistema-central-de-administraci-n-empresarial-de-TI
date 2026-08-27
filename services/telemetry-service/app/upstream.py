from uuid import UUID
import httpx
from .errors import GuardianError
class CoreValidator:
 def __init__(self,s):self.s=s
 def target_for_device(self,device_id:UUID,bearer_token:str):
  try:r=httpx.get(f"{self.s.agent_control_service_url}/internal/v1/devices/{device_id}",headers={"X-Guardian-Internal-Token":self.s.trusted_proxy_token},timeout=5)
  except httpx.HTTPError as exc:raise GuardianError(503,"telemetry.agent_control_unavailable","Agent Control unavailable") from exc
  if r.status_code==404:raise GuardianError(404,"telemetry.device_not_found","Device not found")
  if r.status_code>=400:raise GuardianError(503,"telemetry.agent_control_unavailable","Agent Control unavailable")
  d=r.json();asset_id=UUID(d["guardian_asset_id"]);tenant_id=UUID(d["tenant_id"])
  try:a=httpx.get(f"{self.s.asset_service_url}/api/v1/assets/{asset_id}",headers={"Authorization":f"Bearer {bearer_token}"},timeout=5)
  except httpx.HTTPError as exc:raise GuardianError(503,"telemetry.asset_unavailable","Asset unavailable") from exc
  if a.status_code in {403,404}:raise GuardianError(a.status_code,"telemetry.target_not_accessible","Telemetry target not accessible")
  if a.status_code>=400:raise GuardianError(503,"telemetry.asset_unavailable","Asset unavailable")
  return tenant_id,asset_id
