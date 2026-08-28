package state

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSaveLoadIdentityIsAtomicAndContainsNoEnrollmentToken(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "identity.json")
	in := Identity{DeviceID: "33333333-3333-4333-8333-333333333333", TenantID: "11111111-1111-4111-8111-111111111111", AssetID: "22222222-2222-4222-8222-222222222222", CertificateSerial: "BEEF", CertificatePEM: "cert", CAChainPEM: "chain", ProtectedPrivateKey: "encrypted", SessionID: "55555555-5555-4555-8555-555555555555"}
	if err := Save(path, in); err != nil {
		t.Fatal(err)
	}
	got, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if got != in {
		t.Fatalf("state mismatch: %#v", got)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(strings.ToLower(string(raw)), "token") {
		t.Fatalf("identity state must not persist enrollment token: %s", raw)
	}
	leftovers, _ := filepath.Glob(filepath.Join(dir, ".identity.json-*"))
	if len(leftovers) != 0 {
		t.Fatalf("temporary files left behind: %v", leftovers)
	}
}

func TestNewSessionIDIsUUIDAndStableWhenPersisted(t *testing.T) {
	id, err := NewSessionID()
	if err != nil {
		t.Fatal(err)
	}
	if len(id) != 36 || id[14] != '4' {
		t.Fatalf("unexpected UUID: %q", id)
	}
	dir := t.TempDir()
	path := filepath.Join(dir, "identity.json")
	in := Identity{DeviceID: "d", TenantID: "t", AssetID: "a", CertificateSerial: "s", CertificatePEM: "c", CAChainPEM: "ca", ProtectedPrivateKey: "p", SessionID: id}
	if err := Save(path, in); err != nil {
		t.Fatal(err)
	}
	got, err := Load(path)
	if err != nil {
		t.Fatal(err)
	}
	if got.SessionID != id {
		t.Fatalf("session changed: %q != %q", got.SessionID, id)
	}
}
