package update

import (
	"context"
	"crypto/ed25519"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
)

const maxManifestBytes int64 = 64 << 10

func Stage(client *http.Client, manifestURL string, publicKey ed25519.PublicKey, currentVersion, destination string, maxPayloadBytes int64) (Manifest, error) {
	if client == nil {
		return Manifest{}, errors.New("update HTTP client is required")
	}
	if strings.TrimSpace(destination) == "" || maxPayloadBytes <= 0 {
		return Manifest{}, errors.New("update staging configuration is invalid")
	}
	manifestURI, err := secureURL(manifestURL)
	if err != nil {
		return Manifest{}, fmt.Errorf("update manifest URL: %w", err)
	}
	ctx := context.Background()
	manifestReq, err := http.NewRequestWithContext(ctx, http.MethodGet, manifestURI.String(), nil)
	if err != nil {
		return Manifest{}, err
	}
	manifestReq.Header.Set("Accept", "application/json")
	manifestResp, err := client.Do(manifestReq)
	if err != nil {
		return Manifest{}, fmt.Errorf("download update manifest: %w", err)
	}
	defer manifestResp.Body.Close()
	if manifestResp.Request == nil || manifestResp.Request.URL == nil || manifestResp.Request.URL.Scheme != "https" {
		return Manifest{}, errors.New("update manifest redirect left HTTPS")
	}
	if manifestResp.StatusCode < 200 || manifestResp.StatusCode >= 300 {
		return Manifest{}, fmt.Errorf("update manifest HTTP status %d", manifestResp.StatusCode)
	}
	manifestBody, err := io.ReadAll(io.LimitReader(manifestResp.Body, maxManifestBytes+1))
	if err != nil {
		return Manifest{}, err
	}
	if int64(len(manifestBody)) > maxManifestBytes {
		return Manifest{}, errors.New("update manifest exceeds size limit")
	}
	var manifest Manifest
	decoder := json.NewDecoder(strings.NewReader(string(manifestBody)))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&manifest); err != nil {
		return Manifest{}, fmt.Errorf("decode update manifest: %w", err)
	}
	if err := VerifyManifest(publicKey, manifest, currentVersion); err != nil {
		return Manifest{}, err
	}
	payloadURI, err := secureURL(manifest.URL)
	if err != nil {
		return Manifest{}, fmt.Errorf("update payload URL: %w", err)
	}
	if manifest.Size > maxPayloadBytes {
		return Manifest{}, errors.New("update payload exceeds configured size limit")
	}

	if err := os.MkdirAll(filepath.Dir(destination), 0o700); err != nil {
		return Manifest{}, err
	}
	tmp, err := os.CreateTemp(filepath.Dir(destination), ".update-*")
	if err != nil {
		return Manifest{}, err
	}
	tmpPath := tmp.Name()
	keep := false
	defer func() {
		_ = tmp.Close()
		if !keep {
			_ = os.Remove(tmpPath)
		}
	}()
	if err := tmp.Chmod(0o700); err != nil {
		return Manifest{}, err
	}

	payloadReq, err := http.NewRequestWithContext(ctx, http.MethodGet, payloadURI.String(), nil)
	if err != nil {
		return Manifest{}, err
	}
	payloadReq.Header.Set("Accept", "application/octet-stream")
	payloadResp, err := client.Do(payloadReq)
	if err != nil {
		return Manifest{}, fmt.Errorf("download update payload: %w", err)
	}
	defer payloadResp.Body.Close()
	if payloadResp.Request == nil || payloadResp.Request.URL == nil || payloadResp.Request.URL.Scheme != "https" {
		return Manifest{}, errors.New("update payload redirect left HTTPS")
	}
	if payloadResp.StatusCode < 200 || payloadResp.StatusCode >= 300 {
		return Manifest{}, fmt.Errorf("update payload HTTP status %d", payloadResp.StatusCode)
	}
	limited := io.LimitReader(payloadResp.Body, maxPayloadBytes+1)
	if _, err := io.Copy(tmp, limited); err != nil {
		return Manifest{}, err
	}
	if err := tmp.Sync(); err != nil {
		return Manifest{}, err
	}
	if _, err := tmp.Seek(0, io.SeekStart); err != nil {
		return Manifest{}, err
	}
	if err := VerifyPayload(manifest, tmp, maxPayloadBytes); err != nil {
		return Manifest{}, err
	}
	if err := tmp.Close(); err != nil {
		return Manifest{}, err
	}
	if err := os.Remove(destination); err != nil && !os.IsNotExist(err) {
		return Manifest{}, err
	}
	if err := os.Rename(tmpPath, destination); err != nil {
		return Manifest{}, err
	}
	keep = true
	return manifest, nil
}

func secureURL(raw string) (*url.URL, error) {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || u.Scheme != "https" || u.Host == "" || u.User != nil || u.Fragment != "" {
		return nil, errors.New("URL must be absolute HTTPS without credentials or fragment")
	}
	return u, nil
}
