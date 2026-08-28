package update

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestStageDownloadsSignedManifestAndVerifiedPayloadAtomically(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	payload := []byte("itguardian-agent-next-version")
	var server *httptest.Server
	server = httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/manifest.json":
			h := sha256.Sum256(payload)
			manifest := Manifest{
				Version: "0.8.0",
				URL: server.URL + "/agent.exe",
				SHA256: hex.EncodeToString(h[:]),
				Size: int64(len(payload)),
				PublishedAt: time.Date(2026, 8, 28, 18, 0, 0, 0, time.UTC),
			}
			manifest.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(priv, manifest.CanonicalPayload()))
			_ = json.NewEncoder(w).Encode(manifest)
		case "/agent.exe":
			_, _ = w.Write(payload)
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	destination := filepath.Join(t.TempDir(), "itguardian-agent.staged")
	manifest, err := Stage(server.Client(), server.URL+"/manifest.json", pub, "0.7.0", destination, 64<<20)
	if err != nil {
		t.Fatal(err)
	}
	if manifest.Version != "0.8.0" {
		t.Fatalf("version=%q", manifest.Version)
	}
	got, err := os.ReadFile(destination)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != string(payload) {
		t.Fatalf("payload=%q", got)
	}
	if matches, _ := filepath.Glob(filepath.Join(filepath.Dir(destination), ".update-*")); len(matches) != 0 {
		t.Fatalf("temporary update files leaked: %v", matches)
	}
}

func TestStageRejectsTamperedPayloadAndLeavesNoDestination(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	expected := []byte("expected")
	tampered := []byte("tampered")
	var server *httptest.Server
	server = httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/manifest.json" {
			h := sha256.Sum256(expected)
			manifest := Manifest{Version: "0.8.0", URL: server.URL + "/agent.exe", SHA256: hex.EncodeToString(h[:]), Size: int64(len(expected)), PublishedAt: time.Now().UTC()}
			manifest.Signature = base64.StdEncoding.EncodeToString(ed25519.Sign(priv, manifest.CanonicalPayload()))
			_ = json.NewEncoder(w).Encode(manifest)
			return
		}
		_, _ = w.Write(tampered)
	}))
	defer server.Close()
	destination := filepath.Join(t.TempDir(), "itguardian-agent.staged")
	if _, err := Stage(server.Client(), server.URL+"/manifest.json", pub, "0.7.0", destination, 64<<20); err == nil {
		t.Fatal("expected tampered payload rejection")
	}
	if _, err := os.Stat(destination); !os.IsNotExist(err) {
		t.Fatal("failed update must not leave staged destination")
	}
}
