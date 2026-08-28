package main

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	edgeproxy "github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/services/device-edge-service/internal/proxy"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/services/device-edge-service/internal/revocation"
)

type settings struct {
	listenAddr      string
	tlsCertFile     string
	tlsKeyFile      string
	caChainURL      string
	crlURL          string
	crlRefresh      time.Duration
	agentControlURL string
	commandURL      string
	telemetryURL    string
	proxyToken      string
	maxBodyBytes    int64
}

func main() {
	cfg, err := loadSettings()
	if err != nil {
		log.Fatal(err)
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	client := &http.Client{Timeout: 10 * time.Second}
	chainPEM, err := fetch(ctx, client, cfg.caChainURL, 1<<20)
	if err != nil {
		log.Fatalf("load device CA chain: %v", err)
	}
	clientCAs, issuer, err := parseCAChain(chainPEM)
	if err != nil {
		log.Fatalf("parse device CA chain: %v", err)
	}
	store := revocation.NewStore(issuer)
	if err := refreshCRL(ctx, client, cfg.crlURL, store); err != nil {
		log.Fatalf("load initial device CRL: %v", err)
	}

	handler, err := edgeproxy.New(edgeproxy.Config{
		AgentControlURL: cfg.agentControlURL,
		CommandURL:      cfg.commandURL,
		TelemetryURL:    cfg.telemetryURL,
		ProxyToken:      cfg.proxyToken,
		MaxBodyBytes:    cfg.maxBodyBytes,
		Revocations:     store,
	})
	if err != nil {
		log.Fatal(err)
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health/live", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"status":"ok"}`)
	})
	mux.HandleFunc("/health/ready", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		if !store.Valid(time.Now()) {
			http.Error(w, `{"status":"not_ready","reason":"crl"}`, http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"status":"ready"}`)
	})
	mux.Handle("/", handler)

	server := &http.Server{
		Addr:              cfg.listenAddr,
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
		MaxHeaderBytes:    32 << 10,
		TLSConfig:         &tls.Config{MinVersion: tls.VersionTLS12, ClientAuth: tls.RequireAndVerifyClientCert, ClientCAs: clientCAs},
	}

	go refreshLoop(ctx, client, cfg.crlURL, cfg.crlRefresh, store)
	errCh := make(chan error, 1)
	go func() { errCh <- server.ListenAndServeTLS(cfg.tlsCertFile, cfg.tlsKeyFile) }()
	log.Printf("device edge listening on %s", cfg.listenAddr)
	select {
	case <-ctx.Done():
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer shutdownCancel()
		if err := server.Shutdown(shutdownCtx); err != nil {
			log.Printf("shutdown: %v", err)
		}
	case err := <-errCh:
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatal(err)
		}
	}
}

func loadSettings() (settings, error) {
	maxBody, err := strconv.ParseInt(env("DEVICE_EDGE_MAX_BODY_BYTES", "262144"), 10, 64)
	if err != nil || maxBody <= 0 || maxBody > 2<<20 {
		return settings{}, errors.New("DEVICE_EDGE_MAX_BODY_BYTES must be 1..2097152")
	}
	refreshSeconds, err := strconv.Atoi(env("DEVICE_EDGE_CRL_REFRESH_SECONDS", "300"))
	if err != nil || refreshSeconds < 30 || refreshSeconds > 3600 {
		return settings{}, errors.New("DEVICE_EDGE_CRL_REFRESH_SECONDS must be 30..3600")
	}
	cfg := settings{
		listenAddr:      env("DEVICE_EDGE_LISTEN_ADDR", ":8443"),
		tlsCertFile:     strings.TrimSpace(os.Getenv("DEVICE_EDGE_TLS_CERT_FILE")),
		tlsKeyFile:      strings.TrimSpace(os.Getenv("DEVICE_EDGE_TLS_KEY_FILE")),
		caChainURL:      env("DEVICE_EDGE_CA_CHAIN_URL", "http://pki-service:8004/api/v1/ca/chain"),
		crlURL:          env("DEVICE_EDGE_CRL_URL", "http://pki-service:8004/api/v1/ca/crl"),
		crlRefresh:      time.Duration(refreshSeconds) * time.Second,
		agentControlURL: env("AGENT_CONTROL_SERVICE_URL", "http://agent-control-service:8007"),
		commandURL:      env("COMMAND_SERVICE_URL", "http://command-service:8008"),
		telemetryURL:    env("TELEMETRY_SERVICE_URL", "http://telemetry-service:8009"),
		proxyToken:      strings.TrimSpace(os.Getenv("DEVICE_PROXY_SHARED_SECRET")),
		maxBodyBytes:    maxBody,
	}
	if cfg.tlsCertFile == "" || cfg.tlsKeyFile == "" || cfg.proxyToken == "" {
		return settings{}, errors.New("DEVICE_EDGE_TLS_CERT_FILE, DEVICE_EDGE_TLS_KEY_FILE and DEVICE_PROXY_SHARED_SECRET are required")
	}
	return cfg, nil
}

func env(name, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(name)); v != "" {
		return v
	}
	return fallback
}

func fetch(ctx context.Context, client *http.Client, rawURL string, limit int64) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return nil, err
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("GET %s returned %d", rawURL, resp.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, limit+1))
	if err != nil {
		return nil, err
	}
	if int64(len(body)) > limit {
		return nil, errors.New("PKI public material response too large")
	}
	return body, nil
}

func parseCAChain(chainPEM []byte) (*x509.CertPool, *x509.Certificate, error) {
	pool := x509.NewCertPool()
	remaining := chainPEM
	var issuer *x509.Certificate
	count := 0
	for {
		block, rest := pem.Decode(remaining)
		if block == nil {
			break
		}
		remaining = rest
		if block.Type != "CERTIFICATE" {
			continue
		}
		cert, err := x509.ParseCertificate(block.Bytes)
		if err != nil {
			return nil, nil, err
		}
		if !cert.IsCA {
			return nil, nil, errors.New("device trust chain contains non-CA certificate")
		}
		pool.AddCert(cert)
		count++
		if issuer == nil && !selfSigned(cert) {
			issuer = cert
		}
	}
	if count == 0 {
		return nil, nil, errors.New("device CA chain is empty")
	}
	if issuer == nil {
		return nil, nil, errors.New("device intermediate CA is missing")
	}
	if issuer.KeyUsage&x509.KeyUsageCRLSign == 0 {
		return nil, nil, errors.New("device intermediate cannot sign CRLs")
	}
	return pool, issuer, nil
}

func selfSigned(cert *x509.Certificate) bool {
	return cert != nil && cert.CheckSignatureFrom(cert) == nil
}

func refreshCRL(ctx context.Context, client *http.Client, rawURL string, store *revocation.Store) error {
	data, err := fetch(ctx, client, rawURL, 4<<20)
	if err != nil {
		return err
	}
	block, _ := pem.Decode(data)
	if block == nil || block.Type != "X509 CRL" {
		return errors.New("PKI CRL response is not PEM X509 CRL")
	}
	return store.LoadDER(block.Bytes)
}

func refreshLoop(ctx context.Context, client *http.Client, rawURL string, every time.Duration, store *revocation.Store) {
	ticker := time.NewTicker(every)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := refreshCRL(ctx, client, rawURL, store); err != nil {
				log.Printf("CRL refresh failed; keeping last-good until expiry: %v", err)
			}
		}
	}
}
