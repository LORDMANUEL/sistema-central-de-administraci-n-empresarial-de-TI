import pytest

from app.config import Settings
from app.errors import GatewayError
from app.routes import AuthMode, RouteRegistry
from app.v08_routes import build_v08_route_policies


def registry() -> RouteRegistry:
    return RouteRegistry(build_v08_route_policies(Settings()))


def test_v08_registry_extends_v06_without_duplicates():
    policies = build_v08_route_policies(Settings())
    northbound = [p for p in policies if p.auth_mode != AuthMode.INTERNAL_ONLY]
    internal = [p for p in policies if p.auth_mode == AuthMode.INTERNAL_ONLY]
    assert len(northbound) == 41
    assert len(internal) == 7
    assert len({p.route_id for p in policies}) == len(policies)
    assert len({(p.method, p.path_template) for p in policies}) == len(policies)


def test_v08_agent_control_admin_routes_are_explicit_reads():
    r = registry()
    list_policy = r.require_northbound("GET", "/api/v1/devices").policy
    get_policy = r.require_northbound("GET", "/api/v1/devices/11111111-1111-1111-1111-111111111111").policy
    assert list_policy.route_id == "agent_control.device.list"
    assert get_policy.route_id == "agent_control.device.get"
    assert list_policy.upstream_base_url == "http://agent-control-service:8000"
    assert get_policy.upstream_base_url == "http://agent-control-service:8000"
    assert list_policy.auth_mode == AuthMode.IDENTITY
    assert list_policy.mutation is False
    assert list_policy.audit_intent_required is False


def test_v08_keeps_v06_admin_routes_once():
    r = registry()
    assert r.require_northbound("POST", "/api/v1/commands").policy.route_id == "command.create"
    assert r.require_northbound("GET", "/api/v1/commands").policy.route_id == "command.list"
    assert r.require_northbound("GET", "/api/v1/telemetry/devices/11111111-1111-1111-1111-111111111111/latest").policy.route_id == "telemetry.latest"


def test_device_plane_remains_blocked_from_gateway():
    r = registry()
    for method, path in (
        ("POST", "/api/v1/device/heartbeat"),
        ("POST", "/api/v1/device/commands/acquire"),
        ("POST", "/api/v1/device/telemetry"),
    ):
        with pytest.raises(GatewayError) as raised:
            r.require_northbound(method, path)
        assert raised.value.status_code == 404
        assert raised.value.code == "gateway.route_not_allowed"
