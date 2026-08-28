package config

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

type Runtime struct {
	DeviceEdgeURL              string `json:"device_edge_url"`
	ServerCAPath               string `json:"server_ca_path"`
	StatePath                  string `json:"state_path"`
	SpoolDir                   string `json:"spool_dir"`
	TelemetryIntervalSeconds   int    `json:"telemetry_interval_seconds"`
	UpdateManifestURL          string `json:"update_manifest_url,omitempty"`
	UpdatePublicKey            string `json:"update_public_key,omitempty"`
	UpdateMaxBytes             int64  `json:"update_max_bytes,omitempty"`
	UpdateHealthTimeoutSeconds int    `json:"update_health_timeout_seconds,omitempty"`
}

func DefaultDataDir() string {
	if runtime.GOOS == "windows" {
		base := strings.TrimSpace(os.Getenv("ProgramData"))
		if base == "" {
			base = `C:\ProgramData`
		}
		return filepath.Join(base, "ITGuardian", "Agent")
	}
	if base, err := os.UserConfigDir(); err == nil && base != "" {
		return filepath.Join(base, "itguardian-agent")
	}
	return filepath.Join(os.TempDir(), "itguardian-agent")
}

func Default() Runtime {
	dir := DefaultDataDir()
	return Runtime{
		DeviceEdgeURL:            "https://127.0.0.1:8443",
		ServerCAPath:             filepath.Join(dir, "device-edge-ca.pem"),
		StatePath:                filepath.Join(dir, "identity.json"),
		SpoolDir:                 filepath.Join(dir, "spool"),
		TelemetryIntervalSeconds: 60,
	}
}

func (c Runtime) Validate() error {
	u, err := url.Parse(c.DeviceEdgeURL)
	if err != nil || u.Scheme != "https" || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return errors.New("device_edge_url must be absolute HTTPS without credentials/query/fragment")
	}
	if strings.TrimSpace(c.ServerCAPath) == "" || strings.TrimSpace(c.StatePath) == "" || strings.TrimSpace(c.SpoolDir) == "" {
		return errors.New("server_ca_path, state_path and spool_dir are required")
	}
	if c.TelemetryIntervalSeconds < 15 || c.TelemetryIntervalSeconds > int((15*time.Minute)/time.Second) {
		return errors.New("telemetry_interval_seconds must be between 15 and 900")
	}
	manifestSet := strings.TrimSpace(c.UpdateManifestURL) != ""
	keySet := strings.TrimSpace(c.UpdatePublicKey) != ""
	if manifestSet != keySet {
		return errors.New("update_manifest_url and update_public_key must be configured together")
	}
	if !manifestSet {
		if c.UpdateMaxBytes != 0 || c.UpdateHealthTimeoutSeconds != 0 {
			return errors.New("update limits require update_manifest_url and update_public_key")
		}
		return nil
	}
	updateURL, err := url.Parse(c.UpdateManifestURL)
	if err != nil || updateURL.Scheme != "https" || updateURL.Host == "" || updateURL.User != nil || updateURL.Fragment != "" {
		return errors.New("update_manifest_url must be absolute HTTPS without credentials or fragment")
	}
	if _, err := c.UpdatePublicKeyBytes(); err != nil {
		return err
	}
	if c.UpdateMaxBytes <= 0 || c.UpdateMaxBytes > 256<<20 {
		return errors.New("update_max_bytes must be between 1 and 268435456")
	}
	if c.UpdateHealthTimeoutSeconds < 30 || c.UpdateHealthTimeoutSeconds > 600 {
		return errors.New("update_health_timeout_seconds must be between 30 and 600")
	}
	return nil
}

func (c Runtime) UpdateEnabled() bool {
	return strings.TrimSpace(c.UpdateManifestURL) != "" && strings.TrimSpace(c.UpdatePublicKey) != ""
}

func (c Runtime) UpdatePublicKeyBytes() (ed25519.PublicKey, error) {
	raw, err := base64.StdEncoding.DecodeString(strings.TrimSpace(c.UpdatePublicKey))
	if err != nil || len(raw) != ed25519.PublicKeySize {
		return nil, errors.New("update_public_key must be a base64 Ed25519 public key")
	}
	return ed25519.PublicKey(append([]byte(nil), raw...)), nil
}

func Load(path string) (Runtime, error) {
	f, err := os.Open(path)
	if err != nil {
		return Runtime{}, err
	}
	defer f.Close()
	var cfg Runtime
	dec := json.NewDecoder(io.LimitReader(f, 1<<20))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&cfg); err != nil {
		return Runtime{}, err
	}
	if err := cfg.Validate(); err != nil {
		return Runtime{}, err
	}
	return cfg, nil
}
