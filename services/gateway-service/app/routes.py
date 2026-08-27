from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from starlette.routing import compile_path

from .config import Settings
from .errors import GatewayError


class AuthMode(StrEnum):
    PUBLIC = "public"
    IDENTITY = "identity"
    ENROLLMENT_TOKEN = "enrollment_token"
    INTERNAL_ONLY = "internal_only"


@dataclass(frozen=True)
class RoutePolicy:
    route_id: str
    method: str
    path_template: str
    upstream_base_url: str
    upstream_path_template: str
    auth_mode: AuthMode
    mutation: bool
    audit_intent_required: bool
    max_body_bytes: int
    timeout_seconds: float
    rate_limit_bucket: str


@dataclass(frozen=True)
class RouteMatch:
    policy: RoutePolicy
    path_params: dict[str, str]

    def upstream_path(self) -> str:
        return self.policy.upstream_path_template.format(**self.path_params)


@dataclass(frozen=True)
class _CompiledPolicy:
    policy: RoutePolicy
    regex: object
    convertors: dict


class RouteRegistry:
    def __init__(self, policies: list[RoutePolicy]) -> None:
        route_ids: set[str] = set()
        method_paths: set[tuple[str, str]] = set()
        compiled: list[_CompiledPolicy] = []
        for policy in policies:
            if policy.route_id in route_ids:
                raise ValueError(f"duplicate route_id: {policy.route_id}")
            key = (policy.method.upper(), policy.path_template)
            if key in method_paths:
                raise ValueError(f"duplicate method/path route: {key}")
            if "{path:path}" in policy.path_template or "*" in policy.path_template:
                raise ValueError("catch-all routes are forbidden")
            route_ids.add(policy.route_id)
            method_paths.add(key)
            regex, _, convertors = compile_path(policy.path_template)
            compiled.append(_CompiledPolicy(policy=policy, regex=regex, convertors=convertors))
        self._compiled = tuple(compiled)

    @property
    def policies(self) -> tuple[RoutePolicy, ...]:
        return tuple(item.policy for item in self._compiled)

    def match(self, method: str, path: str, *, include_internal: bool = False) -> RouteMatch | None:
        method = method.upper()
        for item in self._compiled:
            policy = item.policy
            if policy.method != method:
                continue
            if policy.auth_mode == AuthMode.INTERNAL_ONLY and not include_internal:
                continue
            matched = item.regex.match(path)
            if matched is None:
                continue
            params = {
                key: item.convertors[key].convert(value)
                for key, value in matched.groupdict().items()
            }
            return RouteMatch(policy=policy, path_params={key: str(value) for key, value in params.items()})
        return None

    def require_northbound(self, method: str, path: str) -> RouteMatch:
        matched = self.match(method, path, include_internal=False)
        if matched is None:
            raise GatewayError(404, "gateway.route_not_allowed", "Route is not exposed by the Gateway")
        return matched


def _validate_upstream_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("upstream URL must be absolute http/https")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("upstream URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("upstream URL must not contain query or fragment")
    return value.rstrip("/")


def build_route_policies(settings: Settings) -> list[RoutePolicy]:
    identity = _validate_upstream_url(settings.identity_service_url)
    tenant = _validate_upstream_url(settings.tenant_service_url)
    asset = _validate_upstream_url(settings.asset_service_url)
    enrollment = _validate_upstream_url(settings.enrollment_service_url)
    pki = _validate_upstream_url(settings.pki_service_url)
    audit = _validate_upstream_url(settings.audit_service_url)
    command = _validate_upstream_url(settings.command_service_url)
    telemetry = _validate_upstream_url(settings.telemetry_service_url)

    default_body = settings.default_max_body_bytes
    default_timeout = settings.default_timeout_seconds

    def policy(
        route_id: str,
        method: str,
        path: str,
        upstream: str,
        *,
        auth: AuthMode,
        mutation: bool = False,
        audit_required: bool | None = None,
        upstream_path: str | None = None,
        max_body: int | None = None,
        timeout: float | None = None,
        bucket: str | None = None,
    ) -> RoutePolicy:
        if audit_required is None:
            audit_required = mutation and auth == AuthMode.IDENTITY
        if bucket is None:
            if auth == AuthMode.IDENTITY:
                bucket = "admin-write" if mutation else "admin-read"
            elif auth == AuthMode.ENROLLMENT_TOKEN:
                bucket = "endpoint-enrollment"
            else:
                bucket = "public-read"
        return RoutePolicy(
            route_id=route_id,
            method=method.upper(),
            path_template=path,
            upstream_base_url=upstream,
            upstream_path_template=upstream_path or path,
            auth_mode=auth,
            mutation=mutation,
            audit_intent_required=bool(audit_required),
            max_body_bytes=max_body if max_body is not None else default_body,
            timeout_seconds=timeout if timeout is not None else default_timeout,
            rate_limit_bucket=bucket,
        )

    routes = [
        policy("identity.bootstrap", "POST", "/api/v1/auth/bootstrap", identity, auth=AuthMode.PUBLIC, timeout=10, bucket="auth-bootstrap"),
        policy("identity.login", "POST", "/api/v1/auth/login", identity, auth=AuthMode.PUBLIC, timeout=10, bucket="auth-login"),
        policy("identity.refresh", "POST", "/api/v1/auth/refresh", identity, auth=AuthMode.PUBLIC, timeout=10, bucket="auth-login"),
        policy("identity.me", "GET", "/api/v1/users/me", identity, auth=AuthMode.IDENTITY),
        policy("identity.user.create", "POST", "/api/v1/users", identity, auth=AuthMode.IDENTITY, mutation=True),
        policy("identity.user.list", "GET", "/api/v1/users", identity, auth=AuthMode.IDENTITY),
        policy("identity.user.status", "PATCH", "/api/v1/users/{user_id}/status", identity, auth=AuthMode.IDENTITY, mutation=True),

        policy("tenant.create", "POST", "/api/v1/tenants", tenant, auth=AuthMode.IDENTITY, mutation=True),
        policy("tenant.list", "GET", "/api/v1/tenants", tenant, auth=AuthMode.IDENTITY),
        policy("tenant.get", "GET", "/api/v1/tenants/{tenant_id}", tenant, auth=AuthMode.IDENTITY),
        policy("tenant.update", "PATCH", "/api/v1/tenants/{tenant_id}", tenant, auth=AuthMode.IDENTITY, mutation=True),
        policy("tenant.membership.upsert", "POST", "/api/v1/tenants/{tenant_id}/memberships", tenant, auth=AuthMode.IDENTITY, mutation=True),
        policy("tenant.membership.list", "GET", "/api/v1/tenants/{tenant_id}/memberships", tenant, auth=AuthMode.IDENTITY),
        policy("tenant.membership.update", "PATCH", "/api/v1/tenants/{tenant_id}/memberships/{user_id}", tenant, auth=AuthMode.IDENTITY, mutation=True),
        policy("tenant.site.create", "POST", "/api/v1/tenants/{tenant_id}/sites", tenant, auth=AuthMode.IDENTITY, mutation=True),
        policy("tenant.site.list", "GET", "/api/v1/tenants/{tenant_id}/sites", tenant, auth=AuthMode.IDENTITY),
        policy("tenant.site.update", "PATCH", "/api/v1/tenants/{tenant_id}/sites/{site_id}", tenant, auth=AuthMode.IDENTITY, mutation=True),
        policy("tenant.department.create", "POST", "/api/v1/tenants/{tenant_id}/departments", tenant, auth=AuthMode.IDENTITY, mutation=True),
        policy("tenant.department.list", "GET", "/api/v1/tenants/{tenant_id}/departments", tenant, auth=AuthMode.IDENTITY),
        policy("tenant.department.update", "PATCH", "/api/v1/tenants/{tenant_id}/departments/{department_id}", tenant, auth=AuthMode.IDENTITY, mutation=True),

        policy("asset.create", "POST", "/api/v1/assets", asset, auth=AuthMode.IDENTITY, mutation=True),
        policy("asset.list", "GET", "/api/v1/assets", asset, auth=AuthMode.IDENTITY),
        policy("asset.get", "GET", "/api/v1/assets/{asset_id}", asset, auth=AuthMode.IDENTITY),
        policy("asset.external_identity.link", "POST", "/api/v1/assets/{asset_id}/external-identities", asset, auth=AuthMode.IDENTITY, mutation=True),

        policy("enrollment.token.create", "POST", "/api/v1/enrollment-tokens", enrollment, auth=AuthMode.IDENTITY, mutation=True),
        policy("enrollment.token.list", "GET", "/api/v1/enrollment-tokens", enrollment, auth=AuthMode.IDENTITY),
        policy("enrollment.token.revoke", "POST", "/api/v1/enrollment-tokens/{token_id}/revoke", enrollment, auth=AuthMode.IDENTITY, mutation=True),
        policy("enrollment.list", "GET", "/api/v1/enrollments", enrollment, auth=AuthMode.IDENTITY),
        policy("enrollment.get", "GET", "/api/v1/enrollments/{device_id}", enrollment, auth=AuthMode.IDENTITY),
        policy("enrollment.device.enroll", "POST", "/api/v1/enrollments", enrollment, auth=AuthMode.ENROLLMENT_TOKEN, mutation=True, audit_required=False, max_body=256 * 1024, timeout=30, bucket="endpoint-enrollment"),

        policy("audit.records.list", "GET", "/api/v1/audit/records", audit, auth=AuthMode.IDENTITY),
        policy("audit.record.get", "GET", "/api/v1/audit/records/{record_id}", audit, auth=AuthMode.IDENTITY),
        policy("audit.verify", "GET", "/api/v1/audit/verify", audit, auth=AuthMode.IDENTITY),

        policy("pki.crl", "GET", "/api/v1/ca/crl", pki, auth=AuthMode.PUBLIC, timeout=10, bucket="public-read"),

        # v0.6 administrative endpoint-operations plane. Device endpoints deliberately
        # remain outside Gateway bearer-admin routing and use the dedicated trusted edge.
        policy("command.create", "POST", "/api/v1/commands", command, auth=AuthMode.IDENTITY, mutation=True),
        policy("command.list", "GET", "/api/v1/commands", command, auth=AuthMode.IDENTITY),
        policy("command.get", "GET", "/api/v1/commands/{command_id}", command, auth=AuthMode.IDENTITY),
        policy("command.cancel", "POST", "/api/v1/commands/{command_id}/cancel", command, auth=AuthMode.IDENTITY, mutation=True),
        policy("telemetry.latest", "GET", "/api/v1/telemetry/devices/{device_id}/latest", telemetry, auth=AuthMode.IDENTITY),

        policy("tenant.access.internal", "GET", "/api/v1/tenants/{tenant_id}/access", tenant, auth=AuthMode.INTERNAL_ONLY),
        policy("pki.issue.internal", "POST", "/api/v1/certificates/issue", pki, auth=AuthMode.INTERNAL_ONLY, mutation=True, audit_required=False),
        policy("pki.certificates.list.internal", "GET", "/api/v1/certificates", pki, auth=AuthMode.INTERNAL_ONLY),
        policy("pki.certificate.get.internal", "GET", "/api/v1/certificates/{certificate_id}", pki, auth=AuthMode.INTERNAL_ONLY),
        policy("pki.certificate.revoke.internal", "POST", "/api/v1/certificates/{certificate_id}/revoke", pki, auth=AuthMode.INTERNAL_ONLY, mutation=True, audit_required=False),
        policy("identity.jwks.internal", "GET", "/_internal/identity/.well-known/jwks.json", identity, auth=AuthMode.INTERNAL_ONLY, upstream_path="/.well-known/jwks.json"),
        policy("enrollment.jwks.internal", "GET", "/_internal/enrollment/.well-known/jwks.json", enrollment, auth=AuthMode.INTERNAL_ONLY, upstream_path="/.well-known/jwks.json"),
    ]

    if len([item for item in routes if item.auth_mode != AuthMode.INTERNAL_ONLY]) != 39:
        raise AssertionError("unexpected northbound route count")
    if len([item for item in routes if item.auth_mode == AuthMode.INTERNAL_ONLY]) != 7:
        raise AssertionError("unexpected internal-only route count")
    return routes
