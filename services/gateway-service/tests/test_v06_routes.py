from app.config import Settings
from app.routes import AuthMode, RouteRegistry
from app.v06_routes import build_v06_route_policies


def registry():
    return RouteRegistry(build_v06_route_policies(Settings()))


def test_command_admin_routes_are_allowlisted():
    r = registry()
    assert r.require_northbound("POST", "/api/v1/commands").policy.route_id == "command.create"
    assert r.require_northbound("GET", "/api/v1/commands").policy.route_id == "command.list"
    assert r.require_northbound("GET", "/api/v1/commands/7a269974-75d4-4a4d-a89e-583146ae4c44").policy.route_id == "command.get"
    cancel = r.require_northbound("POST", "/api/v1/commands/7a269974-75d4-4a4d-a89e-583146ae4c44/cancel").policy
    assert cancel.route_id == "command.cancel"
    assert cancel.audit_intent_required is True


def test_telemetry_latest_is_admin_read():
    p = registry().require_northbound("GET", "/api/v1/telemetry/devices/7a269974-75d4-4a4d-a89e-583146ae4c44/latest").policy
    assert p.route_id == "telemetry.latest"
    assert p.auth_mode == AuthMode.IDENTITY
    assert p.mutation is False


def test_device_operations_are_not_gateway_routes():
    r = registry()
    assert r.match("POST", "/api/v1/device/heartbeat") is None
    assert r.match("POST", "/api/v1/device/commands/acquire") is None
    assert r.match("POST", "/api/v1/device/telemetry") is None
