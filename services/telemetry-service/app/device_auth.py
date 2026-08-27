from uuid import UUID
from fastapi import Request
from .errors import GuardianError
from .principal import DevicePrincipal
def current_device_principal(request:Request):
 resolver=getattr(request.app.state,"device_principal_resolver",None)
 if resolver:return resolver(request)
 s=request.app.state.settings
 if not s.trusted_proxy_token or request.headers.get("X-Guardian-Proxy-Token","")!=s.trusted_proxy_token:raise GuardianError(401,"device_auth_required","Trusted endpoint authentication required")
 try:return DevicePrincipal(UUID(request.headers["X-Guardian-Tenant-ID"]),UUID(request.headers["X-Guardian-Asset-ID"]),UUID(request.headers["X-Guardian-Device-ID"]),request.headers["X-Guardian-Certificate-Serial"])
 except (KeyError,ValueError) as exc:raise GuardianError(401,"device_auth_invalid","Trusted endpoint identity invalid") from exc
