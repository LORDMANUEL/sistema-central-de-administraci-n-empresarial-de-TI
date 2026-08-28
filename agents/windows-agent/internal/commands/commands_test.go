package commands

import (
	"context"
	"errors"
	"testing"
	"time"
)

type fakePlatform struct {
	rebootDelay int
	service     string
	inventory   int
	rebootErr   error
	serviceErr  error
}

func (f *fakePlatform) Reboot(delaySeconds int) error { f.rebootDelay = delaySeconds; return f.rebootErr }
func (f *fakePlatform) RestartService(name string) error { f.service = name; return f.serviceErr }
func (f *fakePlatform) RefreshInventory(context.Context) error { f.inventory++; return nil }

func TestValidateMirrorsServerCommandAllowlist(t *testing.T) {
	valid := []RemoteCommand{
		{CommandType: "inventory.refresh", Arguments: map[string]any{}},
		{CommandType: "device.reboot", Arguments: map[string]any{"delay_seconds": float64(0)}},
		{CommandType: "device.reboot", Arguments: map[string]any{"delay_seconds": float64(3600)}},
		{CommandType: "service.restart", Arguments: map[string]any{"service_name": "Spooler"}},
	}
	for _, command := range valid {
		if err := Validate(command); err != nil {
			t.Fatalf("%s: %v", command.CommandType, err)
		}
	}
	invalid := []RemoteCommand{
		{CommandType: "shell.exec", Arguments: map[string]any{"command": "whoami"}},
		{CommandType: "inventory.refresh", Arguments: map[string]any{"extra": true}},
		{CommandType: "device.reboot", Arguments: map[string]any{"delay_seconds": float64(3601)}},
		{CommandType: "device.reboot", Arguments: map[string]any{"delay_seconds": 1.5}},
		{CommandType: "service.restart", Arguments: map[string]any{"service_name": "bad&name"}},
		{CommandType: "service.restart", Arguments: map[string]any{"service_name": "Spooler", "extra": true}},
	}
	for _, command := range invalid {
		if err := Validate(command); err == nil {
			t.Fatalf("expected invalid: %#v", command)
		}
	}
}

func TestExecutorUsesPlatformAPIsAndNeverBuildsShell(t *testing.T) {
	p := &fakePlatform{}
	e := Executor{Platform: p, Now: func() time.Time { return time.Date(2026, 8, 28, 15, 0, 0, 0, time.UTC) }}
	result := e.Execute(context.Background(), RemoteCommand{CommandID: "1", CommandType: "inventory.refresh", Arguments: map[string]any{}})
	if result.Status != "succeeded" || p.inventory != 1 {
		t.Fatalf("result=%#v platform=%#v", result, p)
	}
	result = e.Execute(context.Background(), RemoteCommand{CommandID: "2", CommandType: "device.reboot", Arguments: map[string]any{"delay_seconds": float64(30)}})
	if result.Status != "succeeded" || p.rebootDelay != 30 {
		t.Fatalf("result=%#v platform=%#v", result, p)
	}
	result = e.Execute(context.Background(), RemoteCommand{CommandID: "3", CommandType: "service.restart", Arguments: map[string]any{"service_name": "Spooler"}})
	if result.Status != "succeeded" || p.service != "Spooler" {
		t.Fatalf("result=%#v platform=%#v", result, p)
	}
}

func TestExecutorReturnsFailedWithoutPanickingOnPlatformError(t *testing.T) {
	p := &fakePlatform{serviceErr: errors.New("access denied")}
	e := Executor{Platform: p}
	result := e.Execute(context.Background(), RemoteCommand{CommandID: "3", CommandType: "service.restart", Arguments: map[string]any{"service_name": "Spooler"}})
	if result.Status != "failed" || result.ExitCode != 1 || result.Summary == "" {
		t.Fatalf("result=%#v", result)
	}
}
