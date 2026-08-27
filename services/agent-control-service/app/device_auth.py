from uuid import UUID

from fastapi import Request

from .errors import GuardianError
from .principal import DevicePrincipal


def current_device_principal(request: Request) -> DevicePrincipal:
    override = getattr(request.app.state, "device_principal_resolver", None)
    if override is not None:
        return override(request)
    settings = request.app.state.settings
    supplied_proxy_token = request.headers.get("X-Guardian-Proxy-Token", "")
    if not settings.trusted_proxy_token or supplied_proxy_token != settings.trusted_proxy_token:
        raise GuardianError(401, "device_auth_required", "Trusted endpoint authentication is required")
    try:
        return DevicePrincipal(
            tenant_id=UUID(request.headers["X-Guardian-Tenant-ID"]),
            guardian_asset_id=UUID(request.headers["X-Guardian-Asset-ID"]),
            device_id=UUID(request.headers["X-Guardian-Device-ID"]),
            certificate_serial=request.headers["X-Guardian-Certificate-Serial"],
        )
    except (KeyError, ValueError) as exc:
        raise GuardianError(401, "device_auth_invalid", "Trusted endpoint identity is invalid") from exc
