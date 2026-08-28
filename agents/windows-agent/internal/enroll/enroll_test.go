package enroll

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/pem"
	"math/big"
	"net/url"
	"testing"
	"time"
)

const (
	tenantID = "11111111-1111-4111-8111-111111111111"
	assetID  = "22222222-2222-4222-8222-222222222222"
	deviceID = "33333333-3333-4333-8333-333333333333"
)

func issueForKey(t *testing.T, key *ecdsa.PrivateKey, ids [3]string) (certPEM, chainPEM, serialHex, fingerprint string) {
	t.Helper()
	caKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	caTpl := &x509.Certificate{SerialNumber: big.NewInt(10), Subject: pkix.Name{CommonName: "Guardian Test Root"}, NotBefore: now.Add(-time.Hour), NotAfter: now.Add(time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageCRLSign}
	caDER, err := x509.CreateCertificate(rand.Reader, caTpl, caTpl, &caKey.PublicKey, caKey)
	if err != nil {
		t.Fatal(err)
	}
	ca, err := x509.ParseCertificate(caDER)
	if err != nil {
		t.Fatal(err)
	}
	spiffe, _ := url.Parse("spiffe://guardian/tenant/" + ids[0] + "/asset/" + ids[1] + "/device/" + ids[2])
	certTpl := &x509.Certificate{SerialNumber: big.NewInt(0xBEEF), Subject: pkix.Name{CommonName: "host"}, NotBefore: now.Add(-time.Minute), NotAfter: now.Add(30 * time.Minute), URIs: []*url.URL{spiffe}, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}, KeyUsage: x509.KeyUsageDigitalSignature}
	der, err := x509.CreateCertificate(rand.Reader, certTpl, ca, &key.PublicKey, caKey)
	if err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(der)
	return string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})), string(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: caDER})), "BEEF", hex.EncodeToString(sum[:])
}

func TestGenerateCSRUsesP256AndHostnameCN(t *testing.T) {
	key, csrPEM, err := GenerateCSR("PC-001")
	if err != nil {
		t.Fatal(err)
	}
	if key.Curve != elliptic.P256() {
		t.Fatalf("unexpected curve: %T", key.Curve)
	}
	block, _ := pem.Decode([]byte(csrPEM))
	if block == nil {
		t.Fatal("missing PEM CSR")
	}
	csr, err := x509.ParseCertificateRequest(block.Bytes)
	if err != nil {
		t.Fatal(err)
	}
	if csr.Subject.CommonName != "PC-001" || csr.CheckSignature() != nil {
		t.Fatalf("invalid CSR: %#v", csr.Subject)
	}
}

func TestValidateResponseBindsCertificateKeyAndSpiffeIdentity(t *testing.T) {
	key, _, err := GenerateCSR("PC-001")
	if err != nil {
		t.Fatal(err)
	}
	certPEM, chainPEM, serial, fp := issueForKey(t, key, [3]string{tenantID, assetID, deviceID})
	response := EnrollmentResponse{Status: "enrolled", DeviceID: deviceID, TenantID: tenantID, AssetID: assetID, CertificateSerialHex: serial, CertificateFingerprintSHA256: fp, CertificatePEM: certPEM, CAChainPEM: chainPEM}
	cert, err := ValidateResponse(key, response)
	if err != nil {
		t.Fatalf("ValidateResponse: %v", err)
	}
	if cert.SerialNumber.Text(16) != "beef" {
		t.Fatalf("serial=%s", cert.SerialNumber.Text(16))
	}
}

func TestValidateResponseRejectsKeyAndIdentityMismatch(t *testing.T) {
	key, _, _ := GenerateCSR("PC-001")
	other, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	certPEM, chainPEM, serial, fp := issueForKey(t, other, [3]string{tenantID, assetID, deviceID})
	response := EnrollmentResponse{Status: "enrolled", DeviceID: deviceID, TenantID: tenantID, AssetID: assetID, CertificateSerialHex: serial, CertificateFingerprintSHA256: fp, CertificatePEM: certPEM, CAChainPEM: chainPEM}
	if _, err := ValidateResponse(key, response); err == nil {
		t.Fatal("expected key mismatch")
	}

	certPEM, chainPEM, serial, fp = issueForKey(t, key, [3]string{tenantID, assetID, deviceID})
	response = EnrollmentResponse{Status: "enrolled", DeviceID: "44444444-4444-4444-8444-444444444444", TenantID: tenantID, AssetID: assetID, CertificateSerialHex: serial, CertificateFingerprintSHA256: fp, CertificatePEM: certPEM, CAChainPEM: chainPEM}
	if _, err := ValidateResponse(key, response); err == nil {
		t.Fatal("expected identity mismatch")
	}
}
