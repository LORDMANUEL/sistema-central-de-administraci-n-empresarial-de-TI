package proxy

import (
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/services/device-edge-service/internal/identity"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/services/device-edge-service/internal/routes"
)

type RevocationChecker interface {
	IsRevoked(*big.Int) bool
}

type revocationValidity interface {
	Valid(time.Time) bool
}

type Config struct {
	AgentControlURL string
	CommandURL      string
	TelemetryURL    string
	ProxyToken      string
	MaxBodyBytes    int64
	Client          *http.Client
	Revocations     RevocationChecker
}

type Handler struct {
	upstreams   map[string]*url.URL
	proxyToken  string
	maxBody     int64
	client      *http.Client
	revocations RevocationChecker
}

func New(cfg Config) (*Handler, error) {
	if strings.TrimSpace(cfg.ProxyToken) == "" {
		return nil, errors.New("proxy token is required")
	}
	if cfg.MaxBodyBytes <= 0 {
		return nil, errors.New("max body bytes must be positive")
	}
	upstreams := make(map[string]*url.URL, 3)
	for kind, raw := range map[string]string{
		"agent-control": cfg.AgentControlURL,
		"command":       cfg.CommandURL,
		"telemetry":     cfg.TelemetryURL,
	} {
		u, err := url.Parse(raw)
		if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
			return nil, errors.New("invalid upstream URL for " + kind)
		}
		u.Path = strings.TrimSuffix(u.Path, "/")
		upstreams[kind] = u
	}
	client := cfg.Client
	if client == nil {
		client = &http.Client{Timeout: 30 * time.Second}
	}
	return &Handler{upstreams: upstreams, proxyToken: cfg.ProxyToken, maxBody: cfg.MaxBodyBytes, client: client, revocations: cfg.Revocations}, nil
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	target, ok := routes.Match(r.Method, r.URL.Path)
	if !ok {
		writeError(w, http.StatusNotFound, "device_edge.route_not_allowed")
		return
	}
	if r.TLS == nil || len(r.TLS.VerifiedChains) == 0 || len(r.TLS.PeerCertificates) == 0 {
		writeError(w, http.StatusUnauthorized, "device_edge.mtls_required")
		return
	}
	if validity, ok := h.revocations.(revocationValidity); ok && !validity.Valid(time.Now()) {
		writeError(w, http.StatusServiceUnavailable, "device_edge.crl_unavailable")
		return
	}
	cert := r.TLS.PeerCertificates[0]
	if h.revocations != nil && h.revocations.IsRevoked(cert.SerialNumber) {
		writeError(w, http.StatusUnauthorized, "device_edge.certificate_revoked")
		return
	}
	principal, err := identity.FromCertificate(cert)
	if err != nil {
		writeError(w, http.StatusUnauthorized, "device_edge.identity_invalid")
		return
	}
	body, err := io.ReadAll(io.LimitReader(r.Body, h.maxBody+1))
	if err != nil {
		writeError(w, http.StatusBadRequest, "device_edge.body_read_failed")
		return
	}
	if int64(len(body)) > h.maxBody {
		writeError(w, http.StatusRequestEntityTooLarge, "device_edge.body_too_large")
		return
	}
	base := *h.upstreams[target.Kind]
	base.Path = strings.TrimSuffix(base.Path, "/") + target.Path
	base.RawQuery = r.URL.RawQuery
	upstreamReq, err := http.NewRequestWithContext(r.Context(), r.Method, base.String(), strings.NewReader(string(body)))
	if err != nil {
		writeError(w, http.StatusBadGateway, "device_edge.upstream_request_invalid")
		return
	}
	for _, name := range []string{"Content-Type", "Accept", "User-Agent", "X-Request-ID"} {
		if value := r.Header.Get(name); value != "" {
			upstreamReq.Header.Set(name, value)
		}
	}
	upstreamReq.Header.Set("X-Guardian-Proxy-Token", h.proxyToken)
	upstreamReq.Header.Set("X-Guardian-Tenant-ID", principal.TenantID)
	upstreamReq.Header.Set("X-Guardian-Asset-ID", principal.AssetID)
	upstreamReq.Header.Set("X-Guardian-Device-ID", principal.DeviceID)
	upstreamReq.Header.Set("X-Guardian-Certificate-Serial", principal.CertificateSerial)

	resp, err := h.client.Do(upstreamReq)
	if err != nil {
		writeError(w, http.StatusBadGateway, "device_edge.upstream_unavailable")
		return
	}
	defer resp.Body.Close()
	for _, name := range []string{"Content-Type", "Cache-Control", "Retry-After"} {
		if value := resp.Header.Get(name); value != "" {
			w.Header().Set(name, value)
		}
	}
	w.WriteHeader(resp.StatusCode)
	_, _ = io.Copy(w, resp.Body)
}

func writeError(w http.ResponseWriter, status int, code string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]string{"code": code})
}
