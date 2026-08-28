package app

import (
	"bytes"
	"encoding/base64"
	"testing"

	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/enroll"
)

func TestStoredIdentityContainsOnlyProtectedKeyAndCertificateMetadata(t *testing.T) {
	protected := []byte{1, 2, 3, 4}
	response := enroll.EnrollmentResponse{
		DeviceID: "33333333-3333-4333-8333-333333333333",
		TenantID: "11111111-1111-4111-8111-111111111111",
		AssetID: "22222222-2222-4222-8222-222222222222",
		CertificateSerialHex: "ABCD",
		CertificateFingerprintSHA256: "fingerprint",
		CertificatePEM: "CERTIFICATE",
		CAChainPEM: "CHAIN",
	}
	identity := storedIdentity(response, protected, "44444444-4444-4444-8444-444444444444")
	if identity.ProtectedPrivateKey != base64.StdEncoding.EncodeToString(protected) {
		t.Fatalf("protected key=%q", identity.ProtectedPrivateKey)
	}
	if identity.DeviceID != response.DeviceID || identity.SessionID == "" {
		t.Fatalf("identity=%#v", identity)
	}
	decoded, err := base64.StdEncoding.DecodeString(identity.ProtectedPrivateKey)
	if err != nil || !bytes.Equal(decoded, protected) {
		t.Fatalf("decoded=%v err=%v", decoded, err)
	}
}
