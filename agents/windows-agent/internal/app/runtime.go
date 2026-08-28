package app

import (
	"context"
	"crypto/x509"
	"encoding/base64"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"time"

	agentclient "github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/client"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/commands"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/config"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/enroll"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/keystore"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/platform"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/runner"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/spool"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/state"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/telemetry"
)

func EnrollDevice(ctx context.Context, command Command, agentVersion string) error {
	if command.Kind != CommandEnroll {
		return errors.New("enroll command is required")
	}
	key, csrPEM, err := enroll.GenerateCSR(command.Hostname)
	if err != nil {
		return err
	}
	httpClient := &http.Client{Timeout: 30 * time.Second}
	response, err := enroll.RequestEnrollment(ctx, httpClient, command.GatewayURL, command.EnrollmentToken, command.Hostname, agentVersion, csrPEM)
	if err != nil {
		return err
	}
	if _, err := enroll.ValidateResponse(key, response); err != nil {
		return err
	}
	keyDER, err := x509.MarshalECPrivateKey(key)
	if err != nil {
		return err
	}
	defer zero(keyDER)
	protected, err := keystore.Protect(keyDER)
	if err != nil {
		return fmt.Errorf("protect device private key: %w", err)
	}
	sessionID, err := state.NewSessionID()
	if err != nil {
		return err
	}
	identity := storedIdentity(response, protected, sessionID)
	if err := state.Save(command.StatePath, identity); err != nil {
		return fmt.Errorf("persist device identity: %w", err)
	}
	return nil
}

func storedIdentity(response enroll.EnrollmentResponse, protected []byte, sessionID string) state.Identity {
	return state.Identity{
		DeviceID: response.DeviceID,
		TenantID: response.TenantID,
		AssetID: response.AssetID,
		CertificateSerial: response.CertificateSerialHex,
		CertificateFingerprintSHA256: response.CertificateFingerprintSHA256,
		CertificatePEM: response.CertificatePEM,
		CAChainPEM: response.CAChainPEM,
		ProtectedPrivateKey: base64.StdEncoding.EncodeToString(protected),
		SessionID: sessionID,
	}
}

func RunAgent(ctx context.Context, cfg config.Runtime, agentVersion string) error {
	if err := cfg.Validate(); err != nil {
		return err
	}
	identity, err := state.Load(cfg.StatePath)
	if err != nil {
		return fmt.Errorf("load device identity: %w", err)
	}
	protected, err := base64.StdEncoding.DecodeString(identity.ProtectedPrivateKey)
	if err != nil {
		return errors.New("protected private key encoding is invalid")
	}
	keyDER, err := keystore.Unprotect(protected)
	if err != nil {
		return fmt.Errorf("unprotect device private key: %w", err)
	}
	defer zero(keyDER)
	serverCA, err := readBounded(cfg.ServerCAPath, 1<<20)
	if err != nil {
		return fmt.Errorf("load Device Edge server CA: %w", err)
	}
	httpClient, err := agentclient.NewMTLSHTTPClient(identity.CertificatePEM+identity.CAChainPEM, keyDER, serverCA)
	if err != nil {
		return err
	}
	deviceClient, err := agentclient.New(cfg.DeviceEdgeURL, httpClient)
	if err != nil {
		return err
	}
	queue, err := spool.New(cfg.SpoolDir, 64<<20, 10000)
	if err != nil {
		return fmt.Errorf("open endpoint spool: %w", err)
	}
	platformVersion, err := platform.Version()
	if err != nil {
		return fmt.Errorf("read Windows version: %w", err)
	}
	var endpointRunner *runner.Runner
	native := commands.NativePlatform{Refresh: func(refreshCtx context.Context) error {
		if endpointRunner == nil {
			return errors.New("endpoint runner is not ready")
		}
		return endpointRunner.RefreshTelemetry(refreshCtx)
	}}
	endpointRunner = runner.New(runner.Config{
		Client: deviceClient,
		Executor: commands.Executor{Platform: native},
		Spool: queue,
		SessionID: identity.SessionID,
		AgentVersion: agentVersion,
		PlatformVersion: platformVersion,
		Collect: telemetry.Collect,
		TelemetryEvery: time.Duration(cfg.TelemetryIntervalSeconds) * time.Second,
	})
	if err := endpointRunner.Cycle(ctx); err != nil {
		return fmt.Errorf("initial endpoint cycle: %w", err)
	}
	if err := markHealthy(filepath.Join(filepath.Dir(cfg.StatePath), "update-healthy")); err != nil {
		return fmt.Errorf("mark agent healthy: %w", err)
	}
	err = endpointRunner.Run(ctx)
	if errors.Is(err, context.Canceled) {
		return nil
	}
	return err
}

func readBounded(path string, max int64) ([]byte, error) {
	info, err := os.Stat(path)
	if err != nil {
		return nil, err
	}
	if info.Size() <= 0 || info.Size() > max {
		return nil, errors.New("file size is outside policy")
	}
	return os.ReadFile(path)
}

func markHealthy(path string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	return os.WriteFile(path, []byte("ok\n"), 0o600)
}

func zero(data []byte) {
	for i := range data {
		data[i] = 0
	}
}
