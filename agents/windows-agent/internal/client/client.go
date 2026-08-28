package client

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type HeartbeatResponse struct {
	DeviceID                   string    `json:"device_id"`
	ServerTime                 time.Time `json:"server_time"`
	State                      string    `json:"state"`
	HeartbeatIntervalSeconds   int       `json:"heartbeat_interval_seconds"`
	CommandPollIntervalSeconds int       `json:"command_poll_interval_seconds"`
}

type Client struct {
	base *url.URL
	http *http.Client
}

func New(baseURL string, httpClient *http.Client) (*Client, error) {
	u, err := url.Parse(baseURL)
	if err != nil || u.Scheme != "https" || u.Host == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return nil, errors.New("device edge URL must be absolute HTTPS without credentials")
	}
	if httpClient == nil {
		return nil, errors.New("HTTP client is required")
	}
	u.Path = strings.TrimSuffix(u.Path, "/")
	return &Client{base: u, http: httpClient}, nil
}

func NewMTLSHTTPClient(certChainPEM string, keyDER, serverCAPEM []byte) (*http.Client, error) {
	if len(keyDER) == 0 {
		return nil, errors.New("private key DER is required")
	}
	key, err := x509.ParseECPrivateKey(keyDER)
	if err != nil {
		return nil, fmt.Errorf("parse device private key: %w", err)
	}
	var chain [][]byte
	remaining := []byte(certChainPEM)
	for {
		block, rest := pem.Decode(remaining)
		if block == nil {
			break
		}
		remaining = rest
		if block.Type != "CERTIFICATE" {
			continue
		}
		cert, err := x509.ParseCertificate(block.Bytes)
		if err != nil {
			return nil, err
		}
		chain = append(chain, cert.Raw)
	}
	if len(chain) == 0 {
		return nil, errors.New("client certificate chain is invalid")
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(serverCAPEM) {
		return nil, errors.New("server CA PEM is invalid")
	}
	tlsConfig := &tls.Config{
		MinVersion:   tls.VersionTLS12,
		Certificates: []tls.Certificate{{Certificate: chain, PrivateKey: key}},
		RootCAs:      roots,
	}
	transport := &http.Transport{TLSClientConfig: tlsConfig, Proxy: http.ProxyFromEnvironment, ForceAttemptHTTP2: true}
	return &http.Client{Transport: transport, Timeout: 30 * time.Second}, nil
}

func (c *Client) PostJSON(ctx context.Context, path string, payload any, out any) error {
	if c == nil || c.base == nil || c.http == nil {
		return errors.New("device client is not configured")
	}
	if !strings.HasPrefix(path, "/api/v1/device/") {
		return errors.New("device client path is outside device plane")
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	u := *c.base
	u.Path = strings.TrimSuffix(u.Path, "/") + path
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u.String(), bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	resp, err := c.http.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		limited, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return fmt.Errorf("device edge status %d: %s", resp.StatusCode, strings.TrimSpace(string(limited)))
	}
	if out == nil {
		return nil
	}
	decoder := json.NewDecoder(io.LimitReader(resp.Body, 2<<20))
	return decoder.Decode(out)
}
