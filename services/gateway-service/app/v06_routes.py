from .config import Settings
from .routes import AuthMode, RoutePolicy, build_route_policies


def build_v06_route_policies(settings: Settings) -> list[RoutePolicy]:
    routes = list(build_route_policies(settings))
    body = settings.default_max_body_bytes
    timeout = settings.default_timeout_seconds

    def p(route_id: str, method: str, path: str, upstream: str, *, mutation: bool = False, max_body: int | None = None):
        return RoutePolicy(
            route_id=route_id,
            method=method,
            path_template=path,
            upstream_base_url=upstream.rstrip("/"),
            upstream_path_template=path,
            auth_mode=AuthMode.IDENTITY,
            mutation=mutation,
            audit_intent_required=mutation,
            max_body_bytes=max_body if max_body is not None else body,
            timeout_seconds=timeout,
            rate_limit_bucket="admin-write" if mutation else "admin-read",
        )

    routes.extend([
        p("command.create", "POST", "/api/v1/commands", settings.command_service_url, mutation=True, max_body=64 * 1024),
        p("command.list", "GET", "/api/v1/commands", settings.command_service_url),
        p("command.get", "GET", "/api/v1/commands/{command_id}", settings.command_service_url),
        p("command.cancel", "POST", "/api/v1/commands/{command_id}/cancel", settings.command_service_url, mutation=True, max_body=4 * 1024),
        p("telemetry.latest", "GET", "/api/v1/telemetry/devices/{device_id}/latest", settings.telemetry_service_url),
    ])
    return routes
