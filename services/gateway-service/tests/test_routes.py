from __future__ import annotations

import pytest

from app.config import Settings
from app.errors import GatewayError
from app.routes import AuthMode, RouteRegistry, build_route_policies


def settings() -> Settings:
    return Settings(
        identity_service_url="http://identity-service:8000",
        tenant_service_url="http://tenant-service:8000",
        asset_service_url="http://asset-service:8000",
        enrollment_service_url="http://enrollment-service:8000",
        pki_service_url="http://pki-service:8000",
        audit_service_url="http://audit-service:8000",
        agent_control_service_url="http://agent-control-service:8000",
        command_service_url="http://command-service:8000",
        telemetry_service_url="http://telemetry-service:8000",
    )


def registry() -> RouteRegistry:
    return RouteRegistry(build_route_policies(settings()))


def test_initial_registry_is_explicit_unique_and_contains_no_catchall():
    policies = build_route_policies(settings())
    northbound = [policy for policy in policies if policy.auth_mode != AuthMode.INTERNAL_ONLY]
    internal = [policy for policy in policies if policy.auth_mode == AuthMode.INTERNAL_ONLY]

    assert len(northbound) == 41
    assert len(internal) == 7
    assert len({policy.route_id for policy in policies}) == len(policies)
    assert len({(policy.method, policy.path_template) for policy in policies}) == len(policies)
    assert all("{path:path}" not in policy.path_template for policy in policies)
    assert all("*" not in policy.path_template for policy in policies)
    assert all(policy.upstream_base_url.startswith(("http://", "https://")) for policy in policies)


def test_known_static_and_dynamic_routes_resolve_to_fixed_upstreams():
    routes = registry()

    create_tenant = routes.require_northbound("POST", "/api/v1/tenants")
    assert create_tenant.policy.route_id == "tenant.create"
    assert create_tenant.policy.auth_mode == AuthMode.IDENTITY
    assert create_tenant.policy.mutation is True
    assert create_tenant.policy.audit_intent_required is True

    tenants = routes.require_northbound("GET", "/api/v1/tenants")
    assert tenants.policy.route_id == "tenant.list"
    assert tenants.policy.upstream_base_url == "http://tenant-service:8000"
    assert tenants.path_params == {}

    asset = routes.require_northbound("GET", "/api/v1/assets/asset-123")
    assert asset.policy.route_id == "asset.get"
    assert asset.policy.upstream_base_url == "http://asset-service:8000"
    assert asset.path_params == {"asset_id": "asset-123"}


def test_v08_admin_operations_are_explicit_and_device_plane_stays_blocked():
    routes = registry()
    expected = (
        ("GET", "/api/v1/devices", "agent_control.device.list", "http://agent-control-service:8000"),
        ("GET", "/api/v1/devices/11111111-1111-1111-1111-111111111111", "agent_control.device.get", "http://agent-control-service:8000"),
        ("POST", "/api/v1/commands", "command.create", "http://command-service:8000"),
        ("GET", "/api/v1/commands", "command.list", "http://command-service:8000"),
        ("GET", "/api/v1/commands/11111111-1111-1111-1111-111111111111", "command.get", "http://command-service:8000"),
        ("POST", "/api/v1/commands/11111111-1111-1111-1111-111111111111/cancel", "command.cancel", "http://command-service:8000"),
        ("GET", "/api/v1/telemetry/devices/11111111-1111-1111-1111-111111111111/latest", "telemetry.device.latest", "http://telemetry-service:8000"),
    )
    for method, path, route_id, upstream in expected:
        match = routes.require_northbound(method, path)
        assert match.policy.route_id == route_id
        assert match.policy.auth_mode == AuthMode.IDENTITY
        assert match.policy.upstream_base_url == upstream

    for method, path in (
        ("POST", "/api/v1/device/heartbeat"),
        ("POST", "/api/v1/device/commands/acquire"),
        ("POST", "/api/v1/device/telemetry"),
    ):
        assert routes.match(method, path) is None


def test_internal_only_and_unknown_routes_are_not_northbound():
    routes = registry()

    tenant_access = routes.match("GET", "/api/v1/tenants/tenant-1/access", include_internal=True)
    assert tenant_access is not None
    assert tenant_access.policy.auth_mode == AuthMode.INTERNAL_ONLY
    assert routes.match("GET", "/api/v1/tenants/tenant-1/access") is None

    pki_issue = routes.match("POST", "/api/v1/certificates/issue", include_internal=True)
    assert pki_issue is not None
    assert pki_issue.policy.auth_mode == AuthMode.INTERNAL_ONLY
    assert routes.match("POST", "/api/v1/certificates/issue") is None

    for method, path in (
        ("GET", "/.well-known/jwks.json"),
        ("GET", "/api/v1/tenants/tenant-1/access"),
        ("POST", "/api/v1/certificates/issue"),
        ("GET", "/api/v1/not-a-real-route"),
    ):
        with pytest.raises(GatewayError) as raised:
            routes.require_northbound(method, path)
        assert raised.value.status_code == 404
        assert raised.value.code == "gateway.route_not_allowed"


def test_route_security_profiles_are_declared_not_inferred_from_client_input():
    routes = registry()

    login = routes.require_northbound("POST", "/api/v1/auth/login").policy
    assert login.auth_mode == AuthMode.PUBLIC
    assert login.mutation is False
    assert login.audit_intent_required is False
    assert login.timeout_seconds == 10
    assert login.rate_limit_bucket == "auth-login"

    create_tenant = routes.require_northbound("POST", "/api/v1/tenants").policy
    assert create_tenant.auth_mode == AuthMode.IDENTITY
    assert create_tenant.mutation is True
    assert create_tenant.audit_intent_required is True
    assert create_tenant.rate_limit_bucket == "admin-write"

    create_user = routes.require_northbound("POST", "/api/v1/users").policy
    assert create_user.auth_mode == AuthMode.IDENTITY
    assert create_user.mutation is True
    assert create_user.audit_intent_required is True
    assert create_user.rate_limit_bucket == "admin-write"

    enroll = routes.require_northbound("POST", "/api/v1/enrollments").policy
    assert enroll.auth_mode == AuthMode.ENROLLMENT_TOKEN
    assert enroll.mutation is True
    assert enroll.audit_intent_required is False
    assert enroll.max_body_bytes == 256 * 1024
    assert enroll.timeout_seconds == 30
    assert enroll.rate_limit_bucket == "endpoint-enrollment"

    audit = routes.require_northbound("GET", "/api/v1/audit/verify").policy
    assert audit.auth_mode == AuthMode.IDENTITY
    assert audit.mutation is False
    assert audit.upstream_base_url == "http://audit-service:8000"

    command = routes.require_northbound("POST", "/api/v1/commands").policy
    assert command.mutation is True
    assert command.audit_intent_required is True
    assert command.rate_limit_bucket == "admin-write"


def test_wrong_method_does_not_fall_through_to_another_policy():
    routes = registry()
    assert routes.match("DELETE", "/api/v1/assets/asset-123") is None
    with pytest.raises(GatewayError) as raised:
        routes.require_northbound("DELETE", "/api/v1/assets/asset-123")
    assert raised.value.code == "gateway.route_not_allowed"


def test_registry_rejects_upstream_urls_with_credentials():
    bad = settings().model_copy(update={"identity_service_url": "http://user:secret@identity-service:8000"})
    with pytest.raises(ValueError, match="credentials"):
        build_route_policies(bad)
