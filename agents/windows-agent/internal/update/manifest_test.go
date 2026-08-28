package update

import (
	"bytes"
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"testing"
	"time"
)

func signedManifest(t *testing.T, version string, payload []byte) (ed25519.PublicKey, Manifest) {
	t.Helper()
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	h := sha256.Sum256(payload)
	m := Manifest{Version: version, URL: "https://updates.example/itguardian-agent.exe", SHA256: hex.EncodeToString(h[:]), Size: int64(len(payload)), PublishedAt: time.Date(2026, 8, 28, 17, 0, 0, 0, time.UTC)}
	m.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(priv, m.CanonicalPayload()))
	return pub, m
}

func TestVerifyManifestAndPayload(t *testing.T) {
	payload := []byte("agent-binary-v070")
	pub, m := signedManifest(t, "0.7.0", payload)
	if err := VerifyManifest(pub, m, "0.6.0"); err != nil {
		t.Fatal(err)
	}
	if err := VerifyPayload(m, bytes.NewReader(payload), 64<<20); err != nil {
		t.Fatal(err)
	}
}

func TestVerifyManifestRejectsWrongSignatureAndDowngrade(t *testing.T) {
	payload := []byte("agent-binary")
	pub, m := signedManifest(t, "0.6.9", payload)
	m.Signature = base64.StdEncoding.EncodeToString(make([]byte, ed25519.SignatureSize))
	if err := VerifyManifest(pub, m, "0.6.0"); err == nil {
		t.Fatal("expected wrong signature rejection")
	}
	pub, m = signedManifest(t, "0.6.0", payload)
	if err := VerifyManifest(pub, m, "0.7.0"); err == nil {
		t.Fatal("expected downgrade rejection")
	}
}

func TestVerifyPayloadRejectsHashMismatchAndOversize(t *testing.T) {
	pub, m := signedManifest(t, "0.7.0", []byte("expected"))
	if err := VerifyManifest(pub, m, "0.6.0"); err != nil {
		t.Fatal(err)
	}
	if err := VerifyPayload(m, bytes.NewReader([]byte("tampered")), 64<<20); err == nil {
		t.Fatal("expected hash mismatch")
	}
	m.Size = 65 << 20
	if err := VerifyPayload(m, bytes.NewReader(nil), 64<<20); err == nil {
		t.Fatal("expected oversize rejection")
	}
}
