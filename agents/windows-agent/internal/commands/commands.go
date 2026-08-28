package commands

import (
	"context"
	"errors"
	"fmt"
	"math"
	"regexp"
	"strings"
	"time"
)

var serviceNamePattern = regexp.MustCompile(`^[A-Za-z0-9_. -]{1,128}$`)

type RemoteCommand struct {
	CommandID      string         `json:"command_id"`
	CommandType    string         `json:"command_type"`
	Arguments      map[string]any `json:"arguments"`
	ExecutionToken string         `json:"execution_token"`
	LeaseExpiresAt time.Time      `json:"lease_expires_at"`
	ExpiresAt      time.Time      `json:"expires_at"`
}

type Result struct {
	Status     string
	ExitCode   int
	Summary    string
	StartedAt  time.Time
	FinishedAt time.Time
}

type Platform interface {
	Reboot(delaySeconds int) error
	RestartService(name string) error
	RefreshInventory(context.Context) error
}

type Executor struct {
	Platform Platform
	Now      func() time.Time
}

func Validate(command RemoteCommand) error {
	if command.Arguments == nil {
		command.Arguments = map[string]any{}
	}
	switch command.CommandType {
	case "inventory.refresh":
		if len(command.Arguments) != 0 {
			return errors.New("inventory.refresh accepts no arguments")
		}
		return nil
	case "device.reboot":
		if len(command.Arguments) != 1 {
			return errors.New("device.reboot requires exactly delay_seconds")
		}
		value, ok := command.Arguments["delay_seconds"]
		if !ok {
			return errors.New("device.reboot requires delay_seconds")
		}
		delay, ok := integral(value)
		if !ok || delay < 0 || delay > 3600 {
			return errors.New("delay_seconds must be an integer between 0 and 3600")
		}
		return nil
	case "service.restart":
		if len(command.Arguments) != 1 {
			return errors.New("service.restart requires exactly service_name")
		}
		value, ok := command.Arguments["service_name"]
		name, okString := value.(string)
		if !ok || !okString || !serviceNamePattern.MatchString(name) {
			return errors.New("service_name contains unsupported characters or length")
		}
		return nil
	default:
		return fmt.Errorf("unsupported command type: %s", command.CommandType)
	}
}

func (e Executor) Execute(ctx context.Context, command RemoteCommand) Result {
	now := e.Now
	if now == nil {
		now = time.Now
	}
	started := now().UTC()
	result := Result{Status: "failed", ExitCode: 1, StartedAt: started}
	finish := func(err error) Result {
		result.FinishedAt = now().UTC()
		if err == nil {
			result.Status = "succeeded"
			result.ExitCode = 0
			result.Summary = "ok"
		} else {
			result.Summary = truncate(err.Error(), 2048)
		}
		return result
	}
	if e.Platform == nil {
		return finish(errors.New("command platform is unavailable"))
	}
	if err := Validate(command); err != nil {
		return finish(err)
	}
	var err error
	switch command.CommandType {
	case "inventory.refresh":
		err = e.Platform.RefreshInventory(ctx)
	case "device.reboot":
		delay, _ := integral(command.Arguments["delay_seconds"])
		err = e.Platform.Reboot(delay)
	case "service.restart":
		err = e.Platform.RestartService(command.Arguments["service_name"].(string))
	}
	return finish(err)
}

func integral(value any) (int, bool) {
	switch v := value.(type) {
	case int:
		return v, true
	case int32:
		return int(v), true
	case int64:
		if int64(int(v)) != v {
			return 0, false
		}
		return int(v), true
	case float64:
		if math.IsNaN(v) || math.IsInf(v, 0) || math.Trunc(v) != v || v < float64(math.MinInt32) || v > float64(math.MaxInt32) {
			return 0, false
		}
		return int(v), true
	default:
		return 0, false
	}
}

func truncate(value string, max int) string {
	value = strings.TrimSpace(value)
	if len(value) <= max {
		return value
	}
	return value[:max]
}
