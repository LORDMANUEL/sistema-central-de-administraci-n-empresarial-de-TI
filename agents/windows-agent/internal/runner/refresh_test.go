package runner

import (
	"context"
	"testing"
	"time"

	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/commands"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/spool"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/telemetry"
)

func TestRefreshTelemetryUsesNormalTelemetryPipeline(t *testing.T) {
	q, _ := spool.New(t.TempDir(), 1<<20, 100)
	now := time.Now().UTC()
	fc := &fakeClient{}
	r := New(Config{
		Client: fc,
		Executor: commands.Executor{Platform: &fakePlatform{}},
		Spool: q,
		SessionID: "11111111-1111-4111-8111-111111111111",
		AgentVersion: "0.7.0-dev.1",
		PlatformVersion: "Windows 11",
		Collect: func(context.Context) ([]telemetry.Sample, error) {
			return []telemetry.Sample{{Metric: "memory.total_bytes", Value: int64(1), ObservedAt: now}}, nil
		},
		Now: func() time.Time { return now },
	})
	if err := r.RefreshTelemetry(context.Background()); err != nil {
		t.Fatal(err)
	}
	if fc.telemetry != 1 {
		t.Fatalf("telemetry=%d", fc.telemetry)
	}
}
