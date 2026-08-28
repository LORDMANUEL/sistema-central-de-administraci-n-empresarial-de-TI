package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadRejectsEnrollmentTokenPersistence(t *testing.T) {
	p := filepath.Join(t.TempDir(), "agent.json")
	if err := os.WriteFile(p, []byte(`{"device_edge_url":"https://edge.example","server_ca_path":"ca.pem","state_path":"state.json","spool_dir":"spool","enrollment_token":"secret"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := Load(p); err == nil {
		t.Fatal("expected unknown enrollment token field rejection")
	}
}

func TestValidateRequiresHTTPSDeviceEdgeAndBoundedTelemetry(t *testing.T) {
	c := Runtime{DeviceEdgeURL: "http://edge.example", ServerCAPath: "ca.pem", StatePath: "state.json", SpoolDir: "spool", TelemetryIntervalSeconds: 60}
	if err := c.Validate(); err == nil {
		t.Fatal("expected HTTPS rejection")
	}
	c.DeviceEdgeURL = "https://edge.example"
	c.TelemetryIntervalSeconds = 5
	if err := c.Validate(); err == nil {
		t.Fatal("expected telemetry interval rejection")
	}
	c.TelemetryIntervalSeconds = 60
	if err := c.Validate(); err != nil {
		t.Fatal(err)
	}
}
