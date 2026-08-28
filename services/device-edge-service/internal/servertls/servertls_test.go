package servertls

import (
	"bytes"
	"crypto/x509"
	"encoding/pem"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func parseCert(t *testing.T, raw []byte) *x509.Certificate {
	t.Helper()
	block, _ := pem.Decode(raw)
	if block == nil || block.Type != "CERTIFICATE" {
		t.Fatal("certificate PEM missing")
	}
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		t.Fatal(err)
	}
	return cert
}

func TestGenerateCreatesPersistentSeparatedServerTrust(t *testing.T) {
	caDir := filepath.Join(t.TempDir(), "ca")
	runtimeDir := filepath.Join(t.TempDir(), "runtime")
	now := time.Date(2026, 8, 28, 16, 0, 0, 0, time.UTC)
	if err := Generate(caDir, runtimeDir, []string{"localhost", "device-edge-service"}, now); err != nil {
		t.Fatal(err)
	}

	caPEM, err := os.ReadFile(filepath.Join(caDir, "server-ca-cert.pem"))
	if err != nil {
		t.Fatal(err)
	}
	caKey, err := os.ReadFile(filepath.Join(caDir, "server-ca-key.pem"))
	if err != nil || len(caKey) == 0 {
		t.Fatalf("CA key missing: %v", err)
	}
	serverPEM, err := os.ReadFile(filepath.Join(runtimeDir, "server-cert.pem"))
	if err != nil {
		t.Fatal(err)
	}
	serverKey, err := os.ReadFile(filepath.Join(runtimeDir, "server-key.pem"))
	if err != nil || len(serverKey) == 0 {
		t.Fatalf("server key missing: %v", err)
	}
	publicCA, err := os.ReadFile(filepath.Join(runtimeDir, "server-ca.pem"))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(caPEM, publicCA) {
		t.Fatal("runtime public CA must match init CA")
	}
	if _, err := os.Stat(filepath.Join(runtimeDir, "server-ca-key.pem")); !os.IsNotExist(err) {
		t.Fatal("CA private key must not exist in runtime directory")
	}

	ca := parseCert(t, caPEM)
	if !ca.IsCA || ca.CheckSignatureFrom(ca) != nil {
		t.Fatal("server CA must be self-signed CA")
	}
	server := parseCert(t, serverPEM)
	roots := x509.NewCertPool()
	roots.AddCert(ca)
	for _, name := range []string{"localhost", "device-edge-service"} {
		if _, err := server.Verify(x509.VerifyOptions{Roots: roots, DNSName: name, KeyUsages: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}); err != nil {
			t.Fatalf("server certificate does not verify for %s: %v", name, err)
		}
	}

	beforeCA := append([]byte(nil), caPEM...)
	beforeServer := append([]byte(nil), serverPEM...)
	if err := Generate(caDir, runtimeDir, []string{"localhost", "device-edge-service"}, now.Add(time.Hour)); err != nil {
		t.Fatal(err)
	}
	afterCA, _ := os.ReadFile(filepath.Join(caDir, "server-ca-cert.pem"))
	afterServer, _ := os.ReadFile(filepath.Join(runtimeDir, "server-cert.pem"))
	if !bytes.Equal(beforeCA, afterCA) || !bytes.Equal(beforeServer, afterServer) {
		t.Fatal("TLS bootstrap must be idempotent and preserve trust identity")
	}
}

func TestGenerateRejectsUnsafeServerNames(t *testing.T) {
	if err := Generate(t.TempDir(), t.TempDir(), []string{"bad/name"}, time.Now().UTC()); err == nil {
		t.Fatal("expected invalid server name rejection")
	}
}
