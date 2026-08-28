package enroll

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/pem"
	"errors"
	"fmt"
	"net/url"
	"regexp"
	"strings"
	"time"
)

var uuidPattern = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)

type EnrollmentResponse struct {
	Status                       string    `json:"status"`
	DeviceID                     string    `json:"device_id"`
	TenantID                     string    `json:"tenant_id"`
	AssetID                      string    `json:"asset_id"`
	CertificateID                string    `json:"certificate_id"`
	CertificateSerialHex         string    `json:"certificate_serial_hex"`
	CertificateFingerprintSHA256 string    `json:"certificate_fingerprint_sha256"`
	CertificatePEM               string    `json:"certificate_pem"`
	CAChainPEM                   string    `json:"ca_chain_pem"`
	NotBefore                    time.Time `json:"not_before"`
	NotAfter                     time.Time `json:"not_after"`
}

func GenerateCSR(hostname string) (*ecdsa.PrivateKey, string, error) {
	hostname = strings.TrimSpace(hostname)
	if hostname == "" || len(hostname) > 255 {
		return nil, "", errors.New("hostname must contain 1..255 characters")
	}
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return nil, "", err
	}
	der, err := x509.CreateCertificateRequest(rand.Reader, &x509.CertificateRequest{Subject: pkix.Name{CommonName: hostname}}, key)
	if err != nil {
		return nil, "", err
	}
	return key, string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE REQUEST", Bytes: der})), nil
}

func ValidateResponse(key *ecdsa.PrivateKey, response EnrollmentResponse) (*x509.Certificate, error) {
	if key == nil {
		return nil, errors.New("private key is required")
	}
	if response.Status != "enrolled" {
		return nil, errors.New("enrollment response is not enrolled")
	}
	for name, value := range map[string]string{"tenant_id": response.TenantID, "asset_id": response.AssetID, "device_id": response.DeviceID} {
		if !uuidPattern.MatchString(value) {
			return nil, fmt.Errorf("%s is not a UUID", name)
		}
	}
	block, _ := pem.Decode([]byte(response.CertificatePEM))
	if block == nil || block.Type != "CERTIFICATE" {
		return nil, errors.New("device certificate PEM is invalid")
	}
	cert, err := x509.ParseCertificate(block.Bytes)
	if err != nil {
		return nil, err
	}
	certPub, err := x509.MarshalPKIXPublicKey(cert.PublicKey)
	if err != nil {
		return nil, err
	}
	keyPub, err := x509.MarshalPKIXPublicKey(&key.PublicKey)
	if err != nil {
		return nil, err
	}
	if !bytes.Equal(certPub, keyPub) {
		return nil, errors.New("enrollment certificate does not match generated private key")
	}
	if !strings.EqualFold(cert.SerialNumber.Text(16), response.CertificateSerialHex) {
		return nil, errors.New("certificate serial does not match enrollment response")
	}
	fingerprint := sha256.Sum256(cert.Raw)
	if !strings.EqualFold(hex.EncodeToString(fingerprint[:]), response.CertificateFingerprintSHA256) {
		return nil, errors.New("certificate fingerprint does not match enrollment response")
	}
	if err := verifyChain(cert, response.CAChainPEM); err != nil {
		return nil, err
	}
	tenantID, assetID, deviceID, err := spiffeIdentity(cert)
	if err != nil {
		return nil, err
	}
	if tenantID != response.TenantID || assetID != response.AssetID || deviceID != response.DeviceID {
		return nil, errors.New("certificate SPIFFE identity does not match enrollment response")
	}
	return cert, nil
}

func verifyChain(cert *x509.Certificate, chainPEM string) error {
	roots := x509.NewCertPool()
	intermediates := x509.NewCertPool()
	remaining := []byte(chainPEM)
	rootCount := 0
	for {
		block, rest := pem.Decode(remaining)
		if block == nil {
			break
		}
		remaining = rest
		if block.Type != "CERTIFICATE" {
			continue
		}
		ca, err := x509.ParseCertificate(block.Bytes)
		if err != nil {
			return err
		}
		if !ca.IsCA {
			return errors.New("CA chain contains a non-CA certificate")
		}
		if bytes.Equal(ca.RawSubject, ca.RawIssuer) && ca.CheckSignatureFrom(ca) == nil {
			roots.AddCert(ca)
			rootCount++
		} else {
			intermediates.AddCert(ca)
		}
	}
	if rootCount == 0 {
		return errors.New("CA chain does not contain a self-signed trust root")
	}
	_, err := cert.Verify(x509.VerifyOptions{Roots: roots, Intermediates: intermediates, KeyUsages: []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}})
	if err != nil {
		return fmt.Errorf("device certificate chain verification failed: %w", err)
	}
	return nil
}

func spiffeIdentity(cert *x509.Certificate) (string, string, string, error) {
	if cert == nil || len(cert.URIs) != 1 || cert.URIs[0] == nil {
		return "", "", "", errors.New("device certificate must contain exactly one URI SAN")
	}
	u := cert.URIs[0]
	if u.Scheme != "spiffe" || u.Host != "guardian" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return "", "", "", errors.New("device certificate URI SAN is invalid")
	}
	parts := strings.Split(strings.TrimPrefix(u.EscapedPath(), "/"), "/")
	if len(parts) != 6 || parts[0] != "tenant" || parts[2] != "asset" || parts[4] != "device" {
		return "", "", "", errors.New("device certificate URI SAN path is invalid")
	}
	for _, value := range []string{parts[1], parts[3], parts[5]} {
		if !uuidPattern.MatchString(value) {
			return "", "", "", errors.New("device certificate URI SAN contains invalid UUID")
		}
	}
	return parts[1], parts[3], parts[5], nil
}

func EnrollmentURL(base string) (string, error) {
	u, err := url.Parse(base)
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return "", errors.New("gateway URL must be an absolute http/https URL without credentials")
	}
	u.Path = strings.TrimSuffix(u.Path, "/") + "/api/v1/enrollments"
	return u.String(), nil
}
