package client

import (
	"context"
	"errors"
	"fmt"
	"regexp"
	"time"

	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/commands"
)

var canonicalUUID = regexp.MustCompile(`^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$`)

type CommandResultPayload struct {
	ExecutionToken string    `json:"execution_token"`
	ResultSequence int       `json:"result_sequence"`
	Status         string    `json:"status"`
	ExitCode       *int      `json:"exit_code,omitempty"`
	Summary        string    `json:"summary"`
	StartedAt      time.Time `json:"started_at"`
	FinishedAt     time.Time `json:"finished_at"`
}

type CommandResultAck struct {
	ResultID       string `json:"result_id"`
	CommandID      string `json:"command_id"`
	ResultSequence int    `json:"result_sequence"`
	Status         string `json:"status"`
}

type TelemetryAck struct {
	BatchRecordID   string `json:"batch_record_id"`
	AcceptedSamples int    `json:"accepted_samples"`
	Duplicate       bool   `json:"duplicate"`
}

func (c *Client) Heartbeat(ctx context.Context, payload any) (HeartbeatResponse, error) {
	var out HeartbeatResponse
	err := c.PostJSON(ctx, "/api/v1/device/heartbeat", payload, &out)
	return out, err
}

func (c *Client) AcquireCommands(ctx context.Context) ([]commands.RemoteCommand, error) {
	var out []commands.RemoteCommand
	err := c.PostJSON(ctx, "/api/v1/device/commands/acquire", struct{}{}, &out)
	return out, err
}

func (c *Client) MarkRunning(ctx context.Context, commandID, executionToken string) error {
	if err := validateCommandOperation(commandID, executionToken); err != nil {
		return err
	}
	path := fmt.Sprintf("/api/v1/device/commands/%s/running", commandID)
	return c.PostJSON(ctx, path, map[string]string{"execution_token": executionToken}, nil)
}

func (c *Client) SubmitResult(ctx context.Context, commandID string, payload CommandResultPayload) (CommandResultAck, error) {
	var out CommandResultAck
	if err := validateCommandOperation(commandID, payload.ExecutionToken); err != nil {
		return out, err
	}
	if payload.ResultSequence < 1 || (payload.Status != "succeeded" && payload.Status != "failed") {
		return out, errors.New("command result payload is invalid")
	}
	if payload.FinishedAt.Before(payload.StartedAt) {
		return out, errors.New("command result timestamps are invalid")
	}
	path := fmt.Sprintf("/api/v1/device/commands/%s/result", commandID)
	err := c.PostJSON(ctx, path, payload, &out)
	return out, err
}

func (c *Client) SendTelemetry(ctx context.Context, payload any) (TelemetryAck, error) {
	var out TelemetryAck
	err := c.PostJSON(ctx, "/api/v1/device/telemetry", payload, &out)
	return out, err
}

func validateCommandOperation(commandID, executionToken string) error {
	if !canonicalUUID.MatchString(commandID) {
		return errors.New("command ID is invalid")
	}
	if len(executionToken) < 16 || len(executionToken) > 512 {
		return errors.New("execution token length is invalid")
	}
	return nil
}
