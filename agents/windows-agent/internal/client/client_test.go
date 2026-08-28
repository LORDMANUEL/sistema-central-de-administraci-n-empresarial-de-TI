package client

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestDeviceClientNeverSendsTrustedGuardianHeaders(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		for _, name := range []string{"X-Guardian-Proxy-Token", "X-Guardian-Tenant-ID", "X-Guardian-Asset-ID", "X-Guardian-Device-ID", "X-Guardian-Certificate-Serial"} {
			if r.Header.Get(name) != "" {
				t.Fatalf("agent sent trusted header %s", name)
			}
		}
		if r.URL.Path != "/api/v1/device/heartbeat" {
			t.Fatalf("path=%s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"device_id":"33333333-3333-4333-8333-333333333333","server_time":"2026-08-28T15:00:00Z","state":"online","heartbeat_interval_seconds":30,"command_poll_interval_seconds":10}`))
	}))
	defer server.Close()
	c, err := New(server.URL, server.Client())
	if err != nil {
		t.Fatal(err)
	}
	var response HeartbeatResponse
	if err := c.PostJSON(context.Background(), "/api/v1/device/heartbeat", map[string]any{"test": true}, &response); err != nil {
		t.Fatal(err)
	}
	if response.State != "online" || response.HeartbeatIntervalSeconds != 30 {
		t.Fatalf("response=%#v", response)
	}
}

func makeTLSMaterial(t *testing.T) (certPEM string, keyDER, caPEM []byte) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	tpl := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: "client"}, NotBefore: now.Add(-time.Hour), NotAfter: now.Add(time.Hour), KeyUsage: x509.KeyUsageDigitalSignature, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}, IsCA: true, BasicConstraintsValid: true}
	der, err := x509.CreateCertificate(rand.Reader, tpl, tpl, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	keyDER, err = x509.MarshalECPrivateKey(key)
	if err != nil {
		t.Fatal(err)
	}
	return string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})), keyDER, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
}

func TestNewMTLSHTTPClientRejectsInvalidMaterialWithoutInsecureMode(t *testing.T) {
	cert, key, ca := makeTLSMaterial(t)
	httpClient, err := NewMTLSHTTPClient(cert, key, ca)
	if err != nil {
		t.Fatal(err)
	}
	transport, ok := httpClient.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("transport=%T", httpClient.Transport)
	}
	if transport.TLSClientConfig == nil || transport.TLSClientConfig.InsecureSkipVerify {
		t.Fatal("TLS verification must remain enabled")
	}
	if len(transport.TLSClientConfig.Certificates) != 1 || transport.TLSClientConfig.RootCAs == nil {
		t.Fatal("mTLS material missing")
	}
	if _, err := NewMTLSHTTPClient("bad", key, ca); err == nil {
		t.Fatal("expected bad cert error")
	}
}
