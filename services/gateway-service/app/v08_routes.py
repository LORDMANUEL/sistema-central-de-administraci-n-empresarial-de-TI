from __future__ import annotations

from .config import Settings
from .routes import AuthMode, RoutePolicy, _validate_upstream_url
from .v06_routes import build_v06_route_policies


def build_v08_route_policies(settings: Settings) -> list[RoutePolicy]:
    routes = list(build_v06_route_policies(settings))
    agent_control = _validate_upstream_url(settings.agent_control_service_url)
    body = settings.default_max_body_bytes
    timeout = settings.default_timeout_seconds

    def p(route_id: str, path: str) -> RoutePolicy:
        return RoutePolicy(
            route_id=route_id,
            method="GET",
            path_template=path,
            upstream_base_url=agent_control,
            upstream_path_template=path,
            auth_mode=AuthMode.IDENTITY,
            mutation=False,
            audit_intent_required=False,
            max_body_bytes=body,
            timeout_seconds=timeout,
            rate_limit_bucket="admin-read",
        )

    routes.extend([
        p("agent_control.device.list", "/api/v1/devices"),
        p("agent_control.device.get", "/api/v1/devices/{device_id}"),
    ])

    northbound = [item for item in routes if item.auth_mode != AuthMode.INTERNAL_ONLY]
    internal = [item for item in routes if item.auth_mode == AuthMode.INTERNAL_ONLY]
    if len(northbound) != 41:
        raise AssertionError("unexpected v0.8 northbound route count")
    if len(internal) != 7:
        raise AssertionError("unexpected v0.8 internal-only route count")
    return routes
