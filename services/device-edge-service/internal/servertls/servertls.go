package servertls

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"errors"
	"fmt"
	"math/big"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const (
	caCertName     = "server-ca-cert.pem"
	caKeyName      = "server-ca-key.pem"
	serverCertName = "server-cert.pem"
	serverKeyName  = "server-key.pem"
	publicCAName   = "server-ca.pem"
)

func Generate(caDir, runtimeDir string, serverNames []string, now time.Time) error {
	if strings.TrimSpace(caDir) == "" || strings.TrimSpace(runtimeDir) == "" {
		return errors.New("TLS bootstrap directories are required")
	}
	names, err := normalizeNames(serverNames)
	if err != nil {
		return err
	}
	caCertPath := filepath.Join(caDir, caCertName)
	caKeyPath := filepath.Join(caDir, caKeyName)
	serverCertPath := filepath.Join(runtimeDir, serverCertName)
	serverKeyPath := filepath.Join(runtimeDir, serverKeyName)
	publicCAPath := filepath.Join(runtimeDir, publicCAName)
	paths := []string{caCertPath, caKeyPath, serverCertPath, serverKeyPath, publicCAPath}
	present := 0
	for _, path := range paths {
		if _, err := os.Stat(path); err == nil {
			present++
		} else if !os.IsNotExist(err) {
			return err
		}
	}
	if present == len(paths) {
		return validateExisting(caCertPath, serverCertPath, serverKeyPath, publicCAPath, names, now)
	}
	if present != 0 {
		return errors.New("partial Device Edge TLS state exists; refusing trust reset")
	}
	if err := os.MkdirAll(caDir, 0o700); err != nil {
		return err
	}
	if err := os.MkdirAll(runtimeDir, 0o700); err != nil {
		return err
	}
	if now.IsZero() {
		now = time.Now().UTC()
	} else {
		now = now.UTC()
	}

	caKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return err
	}
	caSerial, err := randomSerial()
	if err != nil {
		return err
	}
	caTemplate := &x509.Certificate{
		SerialNumber: caSerial,
		Subject: pkix.Name{Organization: []string{"IT Guardian"}, CommonName: "IT Guardian Device Edge Server CA"},
		NotBefore: now.Add(-5 * time.Minute), NotAfter: now.AddDate(10, 0, 0),
		IsCA: true, BasicConstraintsValid: true,
		KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageCRLSign | x509.KeyUsageDigitalSignature,
	}
	caDER, err := x509.CreateCertificate(rand.Reader, caTemplate, caTemplate, &caKey.PublicKey, caKey)
	if err != nil {
		return err
	}
	caPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: caDER})
	caKeyDER, err := x509.MarshalPKCS8PrivateKey(caKey)
	if err != nil {
		return err
	}
	caKeyPEM := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: caKeyDER})

	serverKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return err
	}
	serverSerial, err := randomSerial()
	if err != nil {
		return err
	}
	serverTemplate := &x509.Certificate{
		SerialNumber: serverSerial,
		Subject: pkix.Name{Organization: []string{"IT Guardian"}, CommonName: names[0]},
		DNSNames: names,
		NotBefore: now.Add(-5 * time.Minute), NotAfter: now.Add(397 * 24 * time.Hour),
		BasicConstraintsValid: true,
		KeyUsage: x509.KeyUsageDigitalSignature,
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	}
	serverDER, err := x509.CreateCertificate(rand.Reader, serverTemplate, caTemplate, &serverKey.PublicKey, caKey)
	if err != nil {
		return err
	}
	serverPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: serverDER})
	serverKeyDER, err := x509.MarshalPKCS8PrivateKey(serverKey)
	if err != nil {
		return err
	}
	serverKeyPEM := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: serverKeyDER})

	for _, item := range []struct {
		path string
		data []byte
		mode os.FileMode
	}{
		{caCertPath, caPEM, 0o644}, {caKeyPath, caKeyPEM, 0o600},
		{serverCertPath, serverPEM, 0o644}, {serverKeyPath, serverKeyPEM, 0o600},
		{publicCAPath, caPEM, 0o644},
	} {
		if err := writeAtomic(item.path, item.data, item.mode); err != nil {
			return err
		}
	}
	return validateExisting(caCertPath, serverCertPath, serverKeyPath, publicCAPath, names, now)
}

func validateExisting(caCertPath, serverCertPath, serverKeyPath, publicCAPath string, names []string, now time.Time) error {
	caPEM, err := os.ReadFile(caCertPath)
	if err != nil {
		return err
	}
	publicCA, err := os.ReadFile(publicCAPath)
	if err != nil {
		return err
	}
	if string(caPEM) != string(publicCA) {
		return errors.New("runtime server CA does not match bootstrap CA")
	}
	caBlock, _ := pem.Decode(caPEM)
	if caBlock == nil {
		return errors.New("server CA PEM invalid")
	}
	ca, err := x509.ParseCertificate(caBlock.Bytes)
	if err != nil || !ca.IsCA || ca.CheckSignatureFrom(ca) != nil {
		return errors.New("server CA certificate invalid")
	}
	serverPEM, err := os.ReadFile(serverCertPath)
	if err != nil {
		return err
	}
	serverBlock, _ := pem.Decode(serverPEM)
	if serverBlock == nil {
		return errors.New("server certificate PEM invalid")
	}
	server, err := x509.ParseCertificate(serverBlock.Bytes)
	if err != nil {
		return err
	}
	keyPEM, err := os.ReadFile(serverKeyPath)
	if err != nil {
		return err
	}
	keyBlock, _ := pem.Decode(keyPEM)
	if keyBlock == nil {
		return errors.New("server private key PEM invalid")
	}
	keyAny, err := x509.ParsePKCS8PrivateKey(keyBlock.Bytes)
	if err != nil {
		return err
	}
	key, ok := keyAny.(*ecdsa.PrivateKey)
	if !ok || !key.PublicKey.Equal(server.PublicKey) {
		return errors.New("server certificate/private key mismatch")
	}
	roots := x509.NewCertPool()
	roots.AddCert(ca)
	if now.IsZero() {
		now = time.Now().UTC()
	}
	for _, name := range names {
		if _, err := server.Verify(x509.VerifyOptions{Roots: roots, DNSName: name, CurrentTime: now, KeyUsages: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}}); err != nil {
			return fmt.Errorf("server certificate verification for %s: %w", name, err)
		}
	}
	return nil
}

func normalizeNames(values []string) ([]string, error) {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(values))
	for _, raw := range values {
		name := strings.ToLower(strings.TrimSpace(raw))
		if !validDNSName(name) {
			return nil, fmt.Errorf("invalid Device Edge server name: %q", raw)
		}
		if _, ok := seen[name]; ok {
			continue
		}
		seen[name] = struct{}{}
		out = append(out, name)
	}
	if len(out) == 0 {
		return nil, errors.New("at least one Device Edge server name is required")
	}
	return out, nil
}

func validDNSName(name string) bool {
	if name == "" || len(name) > 253 || strings.ContainsAny(name, "/\\ :") || strings.Contains(name, "..") {
		return false
	}
	for _, label := range strings.Split(name, ".") {
		if label == "" || len(label) > 63 || label[0] == '-' || label[len(label)-1] == '-' {
			return false
		}
		for _, r := range label {
			if !((r >= 'a' && r <= 'z') || (r >= '0' && r <= '9') || r == '-') {
				return false
			}
		}
	}
	return true
}

func randomSerial() (*big.Int, error) {
	limit := new(big.Int).Lsh(big.NewInt(1), 128)
	serial, err := rand.Int(rand.Reader, limit)
	if err != nil {
		return nil, err
	}
	if serial.Sign() == 0 {
		serial.SetInt64(1)
	}
	return serial, nil
}

func writeAtomic(path string, data []byte, mode os.FileMode) error {
	dir := filepath.Dir(path)
	tmp, err := os.CreateTemp(dir, ".tls-*")
	if err != nil {
		return err
	}
	name := tmp.Name()
	ok := false
	defer func() {
		_ = tmp.Close()
		if !ok {
			_ = os.Remove(name)
		}
	}()
	if err := tmp.Chmod(mode); err != nil {
		return err
	}
	if _, err := tmp.Write(data); err != nil {
		return err
	}
	if err := tmp.Sync(); err != nil {
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Rename(name, path); err != nil {
		return err
	}
	ok = true
	return nil
}
