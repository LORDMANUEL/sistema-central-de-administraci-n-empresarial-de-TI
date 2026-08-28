package client

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"testing"
	"time"
)

type operationsRoundTripFunc func(*http.Request) (*http.Response, error)

func (f operationsRoundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func operationsResponse(status int, body string) *http.Response {
	return &http.Response{StatusCode: status, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(body))}
}

func TestTypedDeviceOperationsUseOnlyAllowlistedPaths(t *testing.T) {
	var paths []string
	hc := &http.Client{Transport: operationsRoundTripFunc(func(r *http.Request) (*http.Response, error) {
		paths = append(paths, r.URL.Path)
		switch {
		case r.URL.Path == "/api/v1/device/heartbeat":
			return operationsResponse(200, `{"device_id":"d","server_time":"2026-08-28T15:00:00Z","state":"online","heartbeat_interval_seconds":30,"command_poll_interval_seconds":5}`), nil
		case r.URL.Path == "/api/v1/device/commands/acquire":
			return operationsResponse(200, `[]`), nil
		case strings.HasSuffix(r.URL.Path, "/running"):
			return operationsResponse(200, `{"command_id":"44444444-4444-4444-8444-444444444444","state":"running"}`), nil
		case strings.HasSuffix(r.URL.Path, "/result"):
			return operationsResponse(200, `{"result_id":"r","command_id":"44444444-4444-4444-8444-444444444444","result_sequence":1,"status":"succeeded"}`), nil
		case r.URL.Path == "/api/v1/device/telemetry":
			return operationsResponse(200, `{"batch_record_id":"b","accepted_samples":2,"duplicate":false}`), nil
		default:
			return operationsResponse(404, `no`), nil
		}
	})}
	c, err := New("https://edge.example", hc)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = c.Heartbeat(context.Background(), map[string]any{"sent_at": time.Now()}); err != nil {
		t.Fatal(err)
	}
	if _, err = c.AcquireCommands(context.Background()); err != nil {
		t.Fatal(err)
	}
	id := "44444444-4444-4444-8444-444444444444"
	if err = c.MarkRunning(context.Background(), id, "abcdefghijklmnop"); err != nil {
		t.Fatal(err)
	}
	if _, err = c.SubmitResult(context.Background(), id, CommandResultPayload{ExecutionToken: "abcdefghijklmnop", ResultSequence: 1, Status: "succeeded", StartedAt: time.Now(), FinishedAt: time.Now()}); err != nil {
		t.Fatal(err)
	}
	if _, err = c.SendTelemetry(context.Background(), map[string]any{"samples": []any{1}}); err != nil {
		t.Fatal(err)
	}
	got, _ := json.Marshal(paths)
	want := `["/api/v1/device/heartbeat","/api/v1/device/commands/acquire","/api/v1/device/commands/44444444-4444-4444-8444-444444444444/running","/api/v1/device/commands/44444444-4444-4444-8444-444444444444/result","/api/v1/device/telemetry"]`
	if string(got) != want {
		t.Fatalf("paths=%s", got)
	}
}

func TestCommandOperationRejectsNonCanonicalCommandID(t *testing.T) {
	c, _ := New("https://edge.example", &http.Client{Transport: operationsRoundTripFunc(func(r *http.Request) (*http.Response, error) {
		t.Fatal("request should not be sent")
		return nil, nil
	})})
	if err := c.MarkRunning(context.Background(), "../commands", "abcdefghijklmnop"); err == nil {
		t.Fatal("expected validation error")
	}
}
