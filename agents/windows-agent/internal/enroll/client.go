package enroll

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
)

type enrollmentRequest struct {
	Token        string `json:"token"`
	Platform     string `json:"platform"`
	Hostname     string `json:"hostname"`
	AgentVersion string `json:"agent_version,omitempty"`
	CSRPEM       string `json:"csr_pem"`
}

func RequestEnrollment(ctx context.Context, client *http.Client, gatewayURL, token, hostname, agentVersion, csrPEM string) (EnrollmentResponse, error) {
	var out EnrollmentResponse
	if client == nil {
		return out, errors.New("HTTP client is required")
	}
	endpoint, err := EnrollmentURL(gatewayURL)
	if err != nil {
		return out, err
	}
	u, _ := url.Parse(endpoint)
	if u.Scheme == "http" && !isLoopbackHost(u.Hostname()) {
		return out, errors.New("unencrypted enrollment is allowed only on loopback")
	}
	if len(token) < 8 || len(token) > 256 {
		return out, errors.New("enrollment token length is invalid")
	}
	if strings.TrimSpace(hostname) == "" || strings.TrimSpace(csrPEM) == "" {
		return out, errors.New("hostname and CSR are required")
	}
	payload, err := json.Marshal(enrollmentRequest{Token: token, Platform: "windows", Hostname: hostname, AgentVersion: agentVersion, CSRPEM: csrPEM})
	if err != nil {
		return out, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(payload))
	if err != nil {
		return out, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	resp, err := client.Do(req)
	if err != nil {
		return out, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return out, fmt.Errorf("enrollment status %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	dec := json.NewDecoder(io.LimitReader(resp.Body, 2<<20))
	if err := dec.Decode(&out); err != nil {
		return out, err
	}
	return out, nil
}

func isLoopbackHost(host string) bool {
	if strings.EqualFold(host, "localhost") {
		return true
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}
