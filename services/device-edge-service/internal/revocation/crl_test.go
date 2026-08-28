package revocation

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"math/big"
	"testing"
	"time"
)

func makeCA(t *testing.T, name string) (*x509.Certificate, *rsa.PrivateKey) {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	tpl := &x509.Certificate{SerialNumber: big.NewInt(1), Subject: pkix.Name{CommonName: name}, NotBefore: now.Add(-time.Hour), NotAfter: now.Add(time.Hour), IsCA: true, BasicConstraintsValid: true, KeyUsage: x509.KeyUsageCertSign | x509.KeyUsageCRLSign}
	der, err := x509.CreateCertificate(rand.Reader, tpl, tpl, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	cert, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatal(err)
	}
	return cert, key
}

func makeCRL(t *testing.T, ca *x509.Certificate, key *rsa.PrivateKey, revoked *big.Int) []byte {
	t.Helper()
	now := time.Now()
	der, err := x509.CreateRevocationList(rand.Reader, &x509.RevocationList{Number: big.NewInt(1), ThisUpdate: now.Add(-time.Minute), NextUpdate: now.Add(time.Hour), RevokedCertificateEntries: []x509.RevocationListEntry{{SerialNumber: revoked, RevocationTime: now.Add(-time.Second)}}}, ca, key)
	if err != nil {
		t.Fatal(err)
	}
	return der
}

func TestStoreRejectsRevokedSerial(t *testing.T) {
	ca, key := makeCA(t, "device-ca")
	store := NewStore(ca)
	if err := store.LoadDER(makeCRL(t, ca, key, big.NewInt(42))); err != nil {
		t.Fatal(err)
	}
	if !store.IsRevoked(big.NewInt(42)) {
		t.Fatal("expected serial revoked")
	}
	if store.IsRevoked(big.NewInt(43)) {
		t.Fatal("unexpected serial revoked")
	}
}

func TestStoreRejectsCRLWithWrongSignerAndKeepsLastGood(t *testing.T) {
	ca, key := makeCA(t, "device-ca")
	other, otherKey := makeCA(t, "other-ca")
	store := NewStore(ca)
	if err := store.LoadDER(makeCRL(t, ca, key, big.NewInt(42))); err != nil {
		t.Fatal(err)
	}
	if err := store.LoadDER(makeCRL(t, other, otherKey, big.NewInt(99))); err == nil {
		t.Fatal("expected signature error")
	}
	if !store.IsRevoked(big.NewInt(42)) {
		t.Fatal("last-good CRL must remain active")
	}
	if store.IsRevoked(big.NewInt(99)) {
		t.Fatal("invalid CRL must not replace state")
	}
}
