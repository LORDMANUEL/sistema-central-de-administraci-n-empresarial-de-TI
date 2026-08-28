package heartbeat

import (
	"testing"
	"time"
)

func TestBuildContainsStableCapabilitiesAndSession(t *testing.T) {
	now := time.Date(2026, 8, 28, 15, 0, 0, 0, time.UTC)
	got := Build("55555555-5555-4555-8555-555555555555", "0.7.0-dev.1", "Windows 11 24H2", now)
	if got.SessionID != "55555555-5555-4555-8555-555555555555" || got.AgentVersion != "0.7.0-dev.1" || got.Platform != "windows" || got.PlatformVersion != "Windows 11 24H2" || !got.SentAt.Equal(now) {
		t.Fatalf("payload=%#v", got)
	}
	if got.CapabilityVersion != 1 {
		t.Fatalf("capability version=%d", got.CapabilityVersion)
	}
	required := map[string]bool{"heartbeat.v1": false, "telemetry.v1": false, "inventory.v1": false, "command.inventory_refresh.v1": false, "command.device_reboot.v1": false, "command.service_restart.v1": false, "spool.v1": false, "update.v1": false}
	for _, capability := range got.Capabilities {
		if _, ok := required[capability]; ok {
			required[capability] = true
		}
	}
	for name, ok := range required {
		if !ok {
			t.Fatalf("missing capability %s", name)
		}
	}
}

func TestClampIntervalsRejectsServerExtremes(t *testing.T) {
	h, c := ClampIntervals(1, 9999)
	if h != 15*time.Second || c != 5*time.Minute {
		t.Fatalf("intervals=%s/%s", h, c)
	}
	h, c = ClampIntervals(30, 10)
	if h != 30*time.Second || c != 10*time.Second {
		t.Fatalf("intervals=%s/%s", h, c)
	}
}
