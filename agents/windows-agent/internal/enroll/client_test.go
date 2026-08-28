package enroll

import (
	"context"
	"io"
	"net/http"
	"strings"
	"testing"
)

type enrollRoundTrip func(*http.Request) (*http.Response, error)

func (f enrollRoundTrip) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestRequestEnrollmentPostsOneTimeTokenWithoutPersistingIt(t *testing.T) {
	hc := &http.Client{Transport: enrollRoundTrip(func(r *http.Request) (*http.Response, error) {
		if r.Method != "POST" || r.URL.String() != "https://gateway.example/api/v1/enrollments" {
			t.Fatalf("request=%s %s", r.Method, r.URL)
		}
		raw, _ := io.ReadAll(r.Body)
		body := string(raw)
		for _, want := range []string{`"token":"one-time-secret"`, `"platform":"windows"`, `"hostname":"pc-01"`, `"agent_version":"0.7.0-dev.1"`, `"csr_pem":"CSR"`} {
			if !strings.Contains(body, want) {
				t.Fatalf("missing %s in %s", want, body)
			}
		}
		return &http.Response{StatusCode: 201, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(`{"status":"enrolled","device_id":"d"}`))}, nil
	})}
	out, err := RequestEnrollment(context.Background(), hc, "https://gateway.example", "one-time-secret", "pc-01", "0.7.0-dev.1", "CSR")
	if err != nil {
		t.Fatal(err)
	}
	if out.Status != "enrolled" || out.DeviceID != "d" {
		t.Fatalf("out=%#v", out)
	}
}

func TestRequestEnrollmentRejectsInsecureRemoteGateway(t *testing.T) {
	hc := &http.Client{Transport: enrollRoundTrip(func(r *http.Request) (*http.Response, error) {
		t.Fatal("request should not happen")
		return nil, nil
	})}
	if _, err := RequestEnrollment(context.Background(), hc, "http://10.0.0.2", "token-token", "pc", "0.7.0", "CSR"); err == nil {
		t.Fatal("expected HTTP remote gateway rejection")
	}
}
