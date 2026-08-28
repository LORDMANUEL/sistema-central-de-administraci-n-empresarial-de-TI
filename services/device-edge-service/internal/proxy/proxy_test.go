package proxy

import (
	"bytes"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"io"
	"math/big"
	"net/http"
	"net/http/httptest"
	"net/url"
	"testing"
	"time"
)

func guardianCert(t *testing.T) *x509.Certificate {
	t.Helper()
	u, err := url.Parse("spiffe://guardian/tenant/11111111-1111-4111-8111-111111111111/asset/22222222-2222-4222-8222-222222222222/device/33333333-3333-4333-8333-333333333333")
	if err != nil {
		t.Fatal(err)
	}
	return &x509.Certificate{SerialNumber: big.NewInt(0xABCD), URIs: []*url.URL{u}}
}

func deviceRequest(t *testing.T, method, path string, body []byte) *http.Request {
	t.Helper()
	r := httptest.NewRequest(method, path, bytes.NewReader(body))
	cert := guardianCert(t)
	r.TLS = &tls.ConnectionState{PeerCertificates: []*x509.Certificate{cert}, VerifiedChains: [][]*x509.Certificate{{cert}}}
	return r
}

func TestHandlerDerivesIdentityAndStripsSpoofableHeaders(t *testing.T) {
	var captured map[string]any
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		captured = map[string]any{
			"path":      r.URL.Path,
			"tenant":    r.Header.Get("X-Guardian-Tenant-ID"),
			"asset":     r.Header.Get("X-Guardian-Asset-ID"),
			"device":    r.Header.Get("X-Guardian-Device-ID"),
			"serial":    r.Header.Get("X-Guardian-Certificate-Serial"),
			"proxy":     r.Header.Get("X-Guardian-Proxy-Token"),
			"forwarded": r.Header.Get("Forwarded"),
			"xff":       r.Header.Get("X-Forwarded-For"),
		}
		w.Header().Set("X-Guardian-Tenant-ID", "must-not-escape")
		w.Header().Set("Connection", "close")
		w.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(w, `{"ok":true}`)
	}))
	defer upstream.Close()

	h, err := New(Config{
		AgentControlURL: upstream.URL,
		CommandURL:      upstream.URL,
		TelemetryURL:    upstream.URL,
		ProxyToken:      "server-only-secret",
		MaxBodyBytes:    1024,
	})
	if err != nil {
		t.Fatal(err)
	}

	req := deviceRequest(t, "POST", "/api/v1/device/heartbeat", []byte(`{"hello":"world"}`))
	req.Header.Set("X-Guardian-Tenant-ID", "attacker")
	req.Header.Set("X-Guardian-Proxy-Token", "attacker")
	req.Header.Set("Forwarded", "for=attacker")
	req.Header.Set("X-Forwarded-For", "attacker")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)

	if rr.Code != 200 {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
	if captured["tenant"] != "11111111-1111-4111-8111-111111111111" || captured["asset"] != "22222222-2222-4222-8222-222222222222" || captured["device"] != "33333333-3333-4333-8333-333333333333" {
		t.Fatalf("identity=%#v", captured)
	}
	if captured["serial"] != "ABCD" || captured["proxy"] != "server-only-secret" {
		t.Fatalf("trusted headers=%#v", captured)
	}
	if captured["forwarded"] != "" || captured["xff"] != "" {
		t.Fatalf("forwarded headers leaked: %#v", captured)
	}
	if rr.Header().Get("X-Guardian-Tenant-ID") != "" || rr.Header().Get("Connection") != "" {
		t.Fatalf("unsafe upstream response headers escaped")
	}
	var body map[string]bool
	if err := json.Unmarshal(rr.Body.Bytes(), &body); err != nil || !body["ok"] {
		t.Fatalf("response=%s err=%v", rr.Body.String(), err)
	}
}

func TestHandlerRejectsUnallowlistedRouteAndUnverifiedPeer(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Fatal("upstream must not be called") }))
	defer upstream.Close()
	h, err := New(Config{AgentControlURL: upstream.URL, CommandURL: upstream.URL, TelemetryURL: upstream.URL, ProxyToken: "secret", MaxBodyBytes: 1024})
	if err != nil {
		t.Fatal(err)
	}

	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, deviceRequest(t, "POST", "/api/v1/commands", nil))
	if rr.Code != http.StatusNotFound {
		t.Fatalf("route status=%d", rr.Code)
	}

	req := httptest.NewRequest("POST", "/api/v1/device/heartbeat", nil)
	req.TLS = &tls.ConnectionState{PeerCertificates: []*x509.Certificate{guardianCert(t)}}
	rr = httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != http.StatusUnauthorized {
		t.Fatalf("unverified status=%d", rr.Code)
	}
}

func TestHandlerEnforcesBodyLimit(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Fatal("upstream must not be called") }))
	defer upstream.Close()
	h, err := New(Config{AgentControlURL: upstream.URL, CommandURL: upstream.URL, TelemetryURL: upstream.URL, ProxyToken: "secret", MaxBodyBytes: 4})
	if err != nil {
		t.Fatal(err)
	}
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, deviceRequest(t, "POST", "/api/v1/device/heartbeat", []byte("12345")))
	if rr.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf("status=%d", rr.Code)
	}
}

type staleRevocations struct{}

func (staleRevocations) IsRevoked(*big.Int) bool { return false }
func (staleRevocations) Valid(time.Time) bool    { return false }

func TestHandlerFailsClosedWhenCRLIsNotCurrent(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Fatal("upstream must not be called") }))
	defer upstream.Close()
	h, err := New(Config{AgentControlURL: upstream.URL, CommandURL: upstream.URL, TelemetryURL: upstream.URL, ProxyToken: "secret", MaxBodyBytes: 1024, Revocations: staleRevocations{}})
	if err != nil {
		t.Fatal(err)
	}
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, deviceRequest(t, "POST", "/api/v1/device/heartbeat", nil))
	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d body=%s", rr.Code, rr.Body.String())
	}
}
