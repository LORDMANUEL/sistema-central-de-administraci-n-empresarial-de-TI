package update

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"
)

type Manifest struct {
	Version     string    `json:"version"`
	URL         string    `json:"url"`
	SHA256      string    `json:"sha256"`
	Size        int64     `json:"size"`
	PublishedAt time.Time `json:"published_at"`
	Signature   string    `json:"signature"`
}

type unsignedManifest struct {
	Version     string `json:"version"`
	URL         string `json:"url"`
	SHA256      string `json:"sha256"`
	Size        int64  `json:"size"`
	PublishedAt string `json:"published_at"`
}

func (m Manifest) CanonicalPayload() []byte {
	payload, _ := json.Marshal(unsignedManifest{
		Version: m.Version,
		URL: m.URL,
		SHA256: strings.ToLower(m.SHA256),
		Size: m.Size,
		PublishedAt: m.PublishedAt.UTC().Format(time.RFC3339Nano),
	})
	return payload
}

func VerifyManifest(publicKey ed25519.PublicKey, m Manifest, currentVersion string) error {
	if len(publicKey) != ed25519.PublicKeySize {
		return errors.New("update public key is invalid")
	}
	if m.Size <= 0 || m.PublishedAt.IsZero() {
		return errors.New("update manifest metadata is incomplete")
	}
	if _, err := hex.DecodeString(m.SHA256); err != nil || len(m.SHA256) != sha256.Size*2 {
		return errors.New("update SHA256 is invalid")
	}
	u, err := url.Parse(m.URL)
	if err != nil || u.Scheme != "https" || u.Host == "" || u.User != nil || u.Fragment != "" {
		return errors.New("update URL must be absolute HTTPS without credentials or fragment")
	}
	newVersion, err := parseVersion(m.Version, false)
	if err != nil {
		return fmt.Errorf("update version: %w", err)
	}
	current, err := parseVersion(currentVersion, true)
	if err != nil {
		return fmt.Errorf("current version: %w", err)
	}
	comparison := compareVersions(newVersion, current)
	if comparison < 0 || (comparison == 0 && current.pre == "") {
		return errors.New("update would downgrade or reinstall the current stable version")
	}
	signature, err := base64.StdEncoding.DecodeString(m.Signature)
	if err != nil || len(signature) != ed25519.SignatureSize {
		return errors.New("update signature encoding is invalid")
	}
	if !ed25519.Verify(publicKey, m.CanonicalPayload(), signature) {
		return errors.New("update manifest signature is invalid")
	}
	return nil
}

func VerifyPayload(m Manifest, reader io.Reader, maxSize int64) error {
	if reader == nil || maxSize <= 0 {
		return errors.New("invalid update payload verification configuration")
	}
	if m.Size <= 0 || m.Size > maxSize {
		return errors.New("update payload exceeds configured size limit")
	}
	h := sha256.New()
	n, err := io.Copy(h, io.LimitReader(reader, maxSize+1))
	if err != nil {
		return err
	}
	if n != m.Size {
		return fmt.Errorf("update payload size mismatch: got %d want %d", n, m.Size)
	}
	got := hex.EncodeToString(h.Sum(nil))
	if !strings.EqualFold(got, m.SHA256) {
		return errors.New("update payload SHA256 mismatch")
	}
	return nil
}

type version struct {
	major int
	minor int
	patch int
	pre   string
}

var versionPattern = regexp.MustCompile(`^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z.-]+))?$`)

func parseVersion(raw string, allowPrerelease bool) (version, error) {
	m := versionPattern.FindStringSubmatch(raw)
	if m == nil {
		return version{}, errors.New("version must use semantic x.y.z form")
	}
	if m[4] != "" && !allowPrerelease {
		return version{}, errors.New("release manifest must not use a prerelease version")
	}
	major, _ := strconv.Atoi(m[1])
	minor, _ := strconv.Atoi(m[2])
	patch, _ := strconv.Atoi(m[3])
	return version{major: major, minor: minor, patch: patch, pre: m[4]}, nil
}

func compareVersions(a, b version) int {
	if a.major != b.major {
		if a.major < b.major {
			return -1
		}
		return 1
	}
	if a.minor != b.minor {
		if a.minor < b.minor {
			return -1
		}
		return 1
	}
	if a.patch != b.patch {
		if a.patch < b.patch {
			return -1
		}
		return 1
	}
	if a.pre == b.pre {
		return 0
	}
	if a.pre == "" {
		return 1
	}
	if b.pre == "" {
		return -1
	}
	if a.pre < b.pre {
		return -1
	}
	return 1
}
