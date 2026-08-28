package runner

import (
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"time"

	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/backoff"
	agentclient "github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/client"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/commands"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/heartbeat"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/spool"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/telemetry"
)

type AgentClient interface {
	Heartbeat(context.Context, any) (agentclient.HeartbeatResponse, error)
	AcquireCommands(context.Context) ([]commands.RemoteCommand, error)
	MarkRunning(context.Context, string, string) error
	SubmitResult(context.Context, string, agentclient.CommandResultPayload) (agentclient.CommandResultAck, error)
	SendTelemetry(context.Context, any) (agentclient.TelemetryAck, error)
}

type Config struct {
	Client          AgentClient
	Executor        commands.Executor
	Spool           *spool.Queue
	SessionID       string
	AgentVersion    string
	PlatformVersion string
	Collect         func(context.Context) ([]telemetry.Sample, error)
	Now             func() time.Time
	TelemetryEvery  time.Duration
}

type Runner struct {
	client          AgentClient
	executor        commands.Executor
	spool           *spool.Queue
	sessionID       string
	agentVersion    string
	platformVersion string
	collect         func(context.Context) ([]telemetry.Sample, error)
	now             func() time.Time
	heartbeatEvery  time.Duration
	commandEvery    time.Duration
	telemetryEvery  time.Duration
}

type storedCommandResult struct {
	CommandID string                           `json:"command_id"`
	Payload   agentclient.CommandResultPayload `json:"payload"`
}

func New(cfg Config) *Runner {
	now := cfg.Now
	if now == nil {
		now = time.Now
	}
	telemetryEvery := cfg.TelemetryEvery
	if telemetryEvery <= 0 {
		telemetryEvery = time.Minute
	}
	return &Runner{
		client: cfg.Client, executor: cfg.Executor, spool: cfg.Spool,
		sessionID: cfg.SessionID, agentVersion: cfg.AgentVersion, platformVersion: cfg.PlatformVersion,
		collect: cfg.Collect, now: now,
		heartbeatEvery: 30 * time.Second, commandEvery: 5 * time.Second, telemetryEvery: telemetryEvery,
	}
}

func (r *Runner) validate() error {
	if r == nil || r.client == nil || r.spool == nil || r.collect == nil {
		return errors.New("runner configuration is incomplete")
	}
	if r.sessionID == "" || r.agentVersion == "" || r.platformVersion == "" {
		return errors.New("runner identity metadata is incomplete")
	}
	return nil
}

// Cycle executes one deterministic endpoint operations cycle. Production scheduling is handled by Run.
func (r *Runner) Cycle(ctx context.Context) error {
	if err := r.validate(); err != nil {
		return err
	}
	if err := r.drain(ctx); err != nil {
		return err
	}
	if err := r.heartbeat(ctx); err != nil {
		return err
	}
	if err := r.telemetry(ctx); err != nil {
		return err
	}
	return r.commands(ctx)
}

func (r *Runner) Run(ctx context.Context) error {
	if err := r.validate(); err != nil {
		return err
	}
	bo := backoff.New(time.Second, 5*time.Minute, nil)
	now := r.now().UTC()
	nextHeartbeat, nextCommand, nextTelemetry := now, now, now
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		now = r.now().UTC()
		var cycleErr error
		if err := r.drain(ctx); err != nil {
			cycleErr = err
		}
		if cycleErr == nil && !now.Before(nextHeartbeat) {
			if err := r.heartbeat(ctx); err != nil {
				cycleErr = err
			} else {
				nextHeartbeat = now.Add(r.heartbeatEvery)
			}
		}
		if cycleErr == nil && !now.Before(nextTelemetry) {
			if err := r.telemetry(ctx); err != nil {
				cycleErr = err
			} else {
				nextTelemetry = now.Add(r.telemetryEvery)
			}
		}
		if cycleErr == nil && !now.Before(nextCommand) {
			if err := r.commands(ctx); err != nil {
				cycleErr = err
			} else {
				nextCommand = now.Add(r.commandEvery)
			}
		}
		if cycleErr != nil {
			if err := sleepContext(ctx, bo.Next()); err != nil {
				return err
			}
			continue
		}
		bo.Reset()
		delay := minDurationUntil(r.now().UTC(), nextHeartbeat, nextCommand, nextTelemetry)
		if delay < 100*time.Millisecond {
			delay = 100 * time.Millisecond
		}
		if err := sleepContext(ctx, delay); err != nil {
			return err
		}
	}
}

func (r *Runner) heartbeat(ctx context.Context) error {
	payload := heartbeat.Build(r.sessionID, r.agentVersion, r.platformVersion, r.now())
	resp, err := r.client.Heartbeat(ctx, payload)
	if err != nil {
		return err
	}
	r.heartbeatEvery, r.commandEvery = heartbeat.ClampIntervals(resp.HeartbeatIntervalSeconds, resp.CommandPollIntervalSeconds)
	return nil
}

func (r *Runner) telemetry(ctx context.Context) error {
	samples, err := r.collect(ctx)
	if err != nil {
		return fmt.Errorf("collect telemetry: %w", err)
	}
	if len(samples) == 0 {
		return nil
	}
	batchID, err := newUUID()
	if err != nil {
		return err
	}
	batch := telemetry.Batch{BatchID: batchID, SentAt: r.now().UTC(), Samples: samples}
	if _, err := r.client.SendTelemetry(ctx, batch); err == nil {
		return nil
	}
	payload, err := json.Marshal(batch)
	if err != nil {
		return err
	}
	return r.spool.Enqueue(spool.Item{Kind: spool.KindTelemetry, ID: batch.BatchID, Payload: payload, CreatedAt: batch.SentAt})
}

func (r *Runner) commands(ctx context.Context) error {
	items, err := r.client.AcquireCommands(ctx)
	if err != nil {
		return err
	}
	now := r.now().UTC()
	for _, command := range items {
		if (!command.LeaseExpiresAt.IsZero() && !now.Before(command.LeaseExpiresAt)) || (!command.ExpiresAt.IsZero() && !now.Before(command.ExpiresAt)) {
			continue
		}
		if err := r.client.MarkRunning(ctx, command.CommandID, command.ExecutionToken); err != nil {
			return err
		}
		result := r.executor.Execute(ctx, command)
		exitCode := result.ExitCode
		payload := agentclient.CommandResultPayload{
			ExecutionToken: command.ExecutionToken,
			ResultSequence: 1,
			Status: result.Status,
			ExitCode: &exitCode,
			Summary: result.Summary,
			StartedAt: result.StartedAt,
			FinishedAt: result.FinishedAt,
		}
		if _, err := r.client.SubmitResult(ctx, command.CommandID, payload); err == nil {
			continue
		}
		stored := storedCommandResult{CommandID: command.CommandID, Payload: payload}
		raw, marshalErr := json.Marshal(stored)
		if marshalErr != nil {
			return marshalErr
		}
		if err := r.spool.Enqueue(spool.Item{Kind: spool.KindCommandResult, ID: command.CommandID + ".1", Payload: raw, CreatedAt: result.FinishedAt}); err != nil {
			return err
		}
	}
	return nil
}

func (r *Runner) drain(ctx context.Context) error {
	items, err := r.spool.List()
	if err != nil {
		return err
	}
	sort.SliceStable(items, func(i, j int) bool {
		return items[i].Kind == spool.KindCommandResult && items[j].Kind != spool.KindCommandResult
	})
	for _, item := range items {
		switch item.Kind {
		case spool.KindCommandResult:
			var stored storedCommandResult
			if err := json.Unmarshal(item.Payload, &stored); err != nil {
				return err
			}
			if _, err := r.client.SubmitResult(ctx, stored.CommandID, stored.Payload); err != nil {
				return err
			}
		case spool.KindTelemetry:
			var batch telemetry.Batch
			if err := json.Unmarshal(item.Payload, &batch); err != nil {
				return err
			}
			if _, err := r.client.SendTelemetry(ctx, batch); err != nil {
				return err
			}
		default:
			return fmt.Errorf("unsupported spool item kind: %s", item.Kind)
		}
		if err := r.spool.Ack(item.Kind, item.ID); err != nil {
			return err
		}
	}
	return nil
}

func newUUID() (string, error) {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", err
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%08x-%04x-%04x-%04x-%012x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16]), nil
}

func minDurationUntil(now time.Time, values ...time.Time) time.Duration {
	var min time.Duration
	for i, value := range values {
		d := value.Sub(now)
		if i == 0 || d < min {
			min = d
		}
	}
	return min
}

func sleepContext(ctx context.Context, d time.Duration) error {
	timer := time.NewTimer(d)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}
