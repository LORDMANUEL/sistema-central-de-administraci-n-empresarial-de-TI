package config

import (
	"crypto/ed25519"
	"crypto/rand"
	"encoding/base64"
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

func TestValidateUpdateConfigurationIsPinnedAndAllOrNothing(t *testing.T) {
	base := Runtime{DeviceEdgeURL: "https://edge.example", ServerCAPath: "ca.pem", StatePath: "state.json", SpoolDir: "spool", TelemetryIntervalSeconds: 60}
	base.UpdateManifestURL = "https://updates.example/manifest.json"
	if err := base.Validate(); err == nil {
		t.Fatal("manifest without pinned public key must fail")
	}
	pub, _, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	base.UpdatePublicKey = base64.StdEncoding.EncodeToString(pub)
	base.UpdateMaxBytes = 64 << 20
	base.UpdateHealthTimeoutSeconds = 120
	if err := base.Validate(); err != nil {
		t.Fatal(err)
	}
	base.UpdateManifestURL = "http://updates.example/manifest.json"
	if err := base.Validate(); err == nil {
		t.Fatal("HTTP update manifest must fail")
	}
	base.UpdateManifestURL = "https://updates.example/manifest.json"
	base.UpdatePublicKey = base64.StdEncoding.EncodeToString([]byte("short"))
	if err := base.Validate(); err == nil {
		t.Fatal("invalid Ed25519 public key must fail")
	}
}
