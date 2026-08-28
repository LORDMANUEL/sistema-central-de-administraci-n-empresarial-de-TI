package main

import "testing"

func TestLoadSettingsUsesInternalComposeServicePorts(t *testing.T) {
	t.Setenv("DEVICE_EDGE_TLS_CERT_FILE", "/tmp/server-cert.pem")
	t.Setenv("DEVICE_EDGE_TLS_KEY_FILE", "/tmp/server-key.pem")
	t.Setenv("DEVICE_PROXY_SHARED_SECRET", "test-only-proxy-secret")
	for _, name := range []string{
		"DEVICE_EDGE_CA_CHAIN_URL", "DEVICE_EDGE_CRL_URL", "AGENT_CONTROL_SERVICE_URL", "COMMAND_SERVICE_URL", "TELEMETRY_SERVICE_URL",
	} {
		t.Setenv(name, "")
	}
	cfg, err := loadSettings()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.caChainURL != "http://pki-service:8000/api/v1/ca/chain" {
		t.Fatalf("CA chain URL=%q", cfg.caChainURL)
	}
	if cfg.crlURL != "http://pki-service:8000/api/v1/ca/crl" {
		t.Fatalf("CRL URL=%q", cfg.crlURL)
	}
	if cfg.agentControlURL != "http://agent-control-service:8000" || cfg.commandURL != "http://command-service:8000" || cfg.telemetryURL != "http://telemetry-service:8000" {
		t.Fatalf("internal upstreams are not using container port 8000: %#v", cfg)
	}
}
