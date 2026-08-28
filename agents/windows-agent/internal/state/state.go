package state

import (
	"crypto/rand"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

type Identity struct {
	DeviceID                     string `json:"device_id"`
	TenantID                     string `json:"tenant_id"`
	AssetID                      string `json:"asset_id"`
	CertificateSerial            string `json:"certificate_serial"`
	CertificateFingerprintSHA256 string `json:"certificate_fingerprint_sha256,omitempty"`
	CertificatePEM               string `json:"certificate_pem"`
	CAChainPEM                   string `json:"ca_chain_pem"`
	ProtectedPrivateKey          string `json:"protected_private_key"`
	SessionID                    string `json:"session_id"`
}

func Save(path string, identity Identity) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return err
	}
	payload, err := json.MarshalIndent(identity, "", "  ")
	if err != nil {
		return err
	}
	tmp, err := os.CreateTemp(dir, "."+filepath.Base(path)+"-*")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	ok := false
	defer func() {
		_ = tmp.Close()
		if !ok {
			_ = os.Remove(tmpName)
		}
	}()
	if err := tmp.Chmod(0o600); err != nil {
		return err
	}
	if _, err := tmp.Write(payload); err != nil {
		return err
	}
	if err := tmp.Sync(); err != nil {
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmpName, path); err != nil {
		return err
	}
	ok = true
	if dirFile, err := os.Open(dir); err == nil {
		_ = dirFile.Sync()
		_ = dirFile.Close()
	}
	return nil
}

func Load(path string) (Identity, error) {
	f, err := os.Open(path)
	if err != nil {
		return Identity{}, err
	}
	defer f.Close()
	limited := io.LimitReader(f, 2<<20)
	var identity Identity
	decoder := json.NewDecoder(limited)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&identity); err != nil {
		return Identity{}, err
	}
	return identity, nil
}

func NewSessionID() (string, error) {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", err
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16]), nil
}
