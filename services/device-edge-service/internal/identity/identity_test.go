package identity

import (
    "crypto/x509"
    "math/big"
    "net/url"
    "testing"
)

const (
    tenantID = "11111111-1111-4111-8111-111111111111"
    assetID  = "22222222-2222-4222-8222-222222222222"
    deviceID = "33333333-3333-4333-8333-333333333333"
)

func mustURI(t *testing.T, raw string) *url.URL {
    t.Helper()
    u, err := url.Parse(raw)
    if err != nil {
        t.Fatal(err)
    }
    return u
}

func TestFromCertificateAcceptsExactlyOneGuardianSpiffeIdentity(t *testing.T) {
    cert := &x509.Certificate{
        SerialNumber: big.NewInt(0x1234ABCD),
        URIs: []*url.URL{mustURI(t, "spiffe://guardian/tenant/" + tenantID + "/asset/" + assetID + "/device/" + deviceID)},
    }
    got, err := FromCertificate(cert)
    if err != nil {
        t.Fatalf("FromCertificate: %v", err)
    }
    if got.TenantID != tenantID || got.AssetID != assetID || got.DeviceID != deviceID {
        t.Fatalf("unexpected principal: %#v", got)
    }
    if got.CertificateSerial != "1234ABCD" {
        t.Fatalf("serial=%q", got.CertificateSerial)
    }
}

func TestFromCertificateRejectsMissingGuardianIdentity(t *testing.T) {
    _, err := FromCertificate(&x509.Certificate{SerialNumber: big.NewInt(1)})
    if err == nil {
        t.Fatal("expected error")
    }
}

func TestFromCertificateRejectsDuplicateGuardianIdentity(t *testing.T) {
    raw := "spiffe://guardian/tenant/" + tenantID + "/asset/" + assetID + "/device/" + deviceID
    cert := &x509.Certificate{SerialNumber: big.NewInt(1), URIs: []*url.URL{mustURI(t, raw), mustURI(t, raw)}}
    if _, err := FromCertificate(cert); err == nil {
        t.Fatal("expected duplicate identity error")
    }
}

func TestFromCertificateRejectsMalformedUUID(t *testing.T) {
    raw := "spiffe://guardian/tenant/not-a-uuid/asset/" + assetID + "/device/" + deviceID
    cert := &x509.Certificate{SerialNumber: big.NewInt(1), URIs: []*url.URL{mustURI(t, raw)}}
    if _, err := FromCertificate(cert); err == nil {
        t.Fatal("expected malformed UUID error")
    }
}
