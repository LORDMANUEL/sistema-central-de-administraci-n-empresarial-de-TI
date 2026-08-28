package runner

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	agentclient "github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/client"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/commands"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/spool"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/telemetry"
)

type fakeClient struct {
	command    []commands.RemoteCommand
	submitErr  error
	submitted  []agentclient.CommandResultPayload
	running    int
	heartbeats int
	telemetry  int
}

func (f *fakeClient) Heartbeat(context.Context, any) (agentclient.HeartbeatResponse, error) {
	f.heartbeats++
	return agentclient.HeartbeatResponse{HeartbeatIntervalSeconds: 30, CommandPollIntervalSeconds: 5, State: "online"}, nil
}
func (f *fakeClient) AcquireCommands(context.Context) ([]commands.RemoteCommand, error) {
	out := f.command
	f.command = nil
	return out, nil
}
func (f *fakeClient) MarkRunning(context.Context, string, string) error { f.running++; return nil }
func (f *fakeClient) SubmitResult(_ context.Context, _ string, p agentclient.CommandResultPayload) (agentclient.CommandResultAck, error) {
	f.submitted = append(f.submitted, p)
	if f.submitErr != nil {
		err := f.submitErr
		f.submitErr = nil
		return agentclient.CommandResultAck{}, err
	}
	return agentclient.CommandResultAck{Status: p.Status}, nil
}
func (f *fakeClient) SendTelemetry(context.Context, any) (agentclient.TelemetryAck, error) {
	f.telemetry++
	return agentclient.TelemetryAck{AcceptedSamples: 1}, nil
}

type fakePlatform struct{ refresh int }

func (p *fakePlatform) Reboot(int) error                   { return nil }
func (p *fakePlatform) RestartService(string) error       { return nil }
func (p *fakePlatform) RefreshInventory(context.Context) error { p.refresh++; return nil }

func TestCycleSpoolsFailedTerminalResultAndNextCycleDrainsSamePayload(t *testing.T) {
	q, _ := spool.New(t.TempDir(), 1<<20, 100)
	now := time.Date(2026, 8, 28, 16, 0, 0, 0, time.UTC)
	fc := &fakeClient{
		submitErr: errors.New("network down"),
		command: []commands.RemoteCommand{{
			CommandID: "44444444-4444-4444-8444-444444444444", CommandType: "inventory.refresh", Arguments: map[string]any{},
			ExecutionToken: "abcdefghijklmnop", LeaseExpiresAt: now.Add(time.Minute), ExpiresAt: now.Add(time.Hour),
		}},
	}
	platform := &fakePlatform{}
	r := New(Config{
		Client: fc, Executor: commands.Executor{Platform: platform, Now: func() time.Time { return now }}, Spool: q,
		SessionID: "11111111-1111-4111-8111-111111111111", AgentVersion: "0.7.0-dev.1", PlatformVersion: "Windows 11",
		Collect: func(context.Context) ([]telemetry.Sample, error) {
			return []telemetry.Sample{{Metric: "memory.total_bytes", Value: int64(8 << 30), ObservedAt: now}}, nil
		},
		Now: func() time.Time { return now },
	})
	if err := r.Cycle(context.Background()); err != nil {
		t.Fatal(err)
	}
	if platform.refresh != 1 || fc.running != 1 || len(fc.submitted) != 1 {
		t.Fatalf("execute=%d running=%d submitted=%d", platform.refresh, fc.running, len(fc.submitted))
	}
	items, err := q.List()
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].Kind != spool.KindCommandResult {
		t.Fatalf("spool=%#v", items)
	}
	var stored storedCommandResult
	if err := json.Unmarshal(items[0].Payload, &stored); err != nil {
		t.Fatal(err)
	}
	first := fc.submitted[0]
	if stored.CommandID != "44444444-4444-4444-8444-444444444444" || stored.Payload.ExecutionToken != first.ExecutionToken || stored.Payload.Status != first.Status {
		t.Fatalf("stored=%#v first=%#v", stored, first)
	}
	if err := r.Cycle(context.Background()); err != nil {
		t.Fatal(err)
	}
	if platform.refresh != 1 {
		t.Fatalf("command re-executed: %d", platform.refresh)
	}
	if len(fc.submitted) != 2 {
		t.Fatalf("submitted=%d", len(fc.submitted))
	}
	if fc.submitted[1].ExecutionToken != first.ExecutionToken || fc.submitted[1].StartedAt != first.StartedAt || fc.submitted[1].FinishedAt != first.FinishedAt {
		t.Fatalf("payload changed: %#v vs %#v", fc.submitted[1], first)
	}
	items, _ = q.List()
	if len(items) != 0 {
		t.Fatalf("spool not drained: %#v", items)
	}
}

func TestCycleSendsHeartbeatAndTelemetry(t *testing.T) {
	q, _ := spool.New(t.TempDir(), 1<<20, 100)
	now := time.Now().UTC()
	fc := &fakeClient{}
	r := New(Config{
		Client: fc, Executor: commands.Executor{Platform: &fakePlatform{}}, Spool: q,
		SessionID: "11111111-1111-4111-8111-111111111111", AgentVersion: "0.7.0-dev.1", PlatformVersion: "Windows 11",
		Collect: func(context.Context) ([]telemetry.Sample, error) {
			return []telemetry.Sample{{Metric: "memory.total_bytes", Value: int64(1), ObservedAt: now}}, nil
		},
		Now: func() time.Time { return now },
	})
	if err := r.Cycle(context.Background()); err != nil {
		t.Fatal(err)
	}
	if fc.heartbeats != 1 || fc.telemetry != 1 {
		t.Fatalf("heartbeats=%d telemetry=%d", fc.heartbeats, fc.telemetry)
	}
}
