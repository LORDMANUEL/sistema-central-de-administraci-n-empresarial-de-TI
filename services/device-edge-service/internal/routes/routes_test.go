package routes

import "testing"

func TestMatchAllowsOnlyDevicePlaneRoutes(t *testing.T) {
    allowed := []struct{ method, path, kind string }{
        {"POST", "/api/v1/device/heartbeat", "agent-control"},
        {"POST", "/api/v1/device/commands/acquire", "command"},
        {"POST", "/api/v1/device/commands/44444444-4444-4444-8444-444444444444/running", "command"},
        {"POST", "/api/v1/device/commands/44444444-4444-4444-8444-444444444444/result", "command"},
        {"POST", "/api/v1/device/telemetry", "telemetry"},
    }
    for _, tc := range allowed {
        target, ok := Match(tc.method, tc.path)
        if !ok {
            t.Fatalf("expected route allowed: %s %s", tc.method, tc.path)
        }
        if target.Kind != tc.kind || target.Path != tc.path {
            t.Fatalf("unexpected target: %#v", target)
        }
    }

    denied := [][2]string{
        {"GET", "/api/v1/device/heartbeat"},
        {"POST", "/api/v1/commands"},
        {"POST", "/api/v1/device/commands/not-a-uuid/result"},
        {"POST", "/api/v1/device/commands/44444444-4444-4444-8444-444444444444/cancel"},
        {"GET", "/api/v1/audit/records"},
    }
    for _, tc := range denied {
        if _, ok := Match(tc[0], tc[1]); ok {
            t.Fatalf("route must be denied: %s %s", tc[0], tc[1])
        }
    }
}
