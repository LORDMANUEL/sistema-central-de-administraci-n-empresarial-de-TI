package main

import (
	"context"
	"errors"
	"fmt"
	"log"
	"os"
	"os/signal"
	"time"

	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/app"
	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/config"
	agentservice "github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/service"
)

var version = "0.7.0-dev.1"

func main() {
	if err := run(os.Args[1:]); err != nil {
		log.Printf("itguardian-agent: %v", err)
		os.Exit(1)
	}
}

func run(args []string) error {
	command, err := app.ParseArgs(args)
	if err != nil {
		return err
	}
	switch command.Kind {
	case app.CommandVersion:
		fmt.Println(version)
		return nil
	case app.CommandEnroll:
		ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
		defer cancel()
		if err := app.EnrollDevice(ctx, command, version); err != nil {
			return err
		}
		fmt.Printf("IT Guardian enrollment completed; identity stored at %s\n", command.StatePath)
		return nil
	case app.CommandRun:
		cfg, err := config.Load(command.ConfigPath)
		if err != nil {
			return fmt.Errorf("load runtime config: %w", err)
		}
		worker := func(ctx context.Context) error { return app.RunAgent(ctx, cfg, version) }
		isService, err := agentservice.IsWindowsService()
		if err != nil {
			return fmt.Errorf("detect Windows service: %w", err)
		}
		if isService {
			return agentservice.RunWindowsService(worker)
		}
		ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt)
		defer cancel()
		err = agentservice.RunForeground(ctx, worker)
		if errors.Is(err, context.Canceled) {
			return nil
		}
		return err
	case app.CommandUpdate:
		cfg, err := config.Load(command.ConfigPath)
		if err != nil {
			return fmt.Errorf("load runtime config: %w", err)
		}
		ctx, cancel := context.WithTimeout(context.Background(), 6*time.Minute)
		defer cancel()
		nextVersion, err := app.PrepareUpdate(ctx, cfg, version)
		if err != nil {
			return err
		}
		fmt.Printf("IT Guardian signed update %s staged; transactional helper launched\n", nextVersion)
		return nil
	case app.CommandApplyUpdate:
		deadline := time.Unix(command.DeadlineUnix, 0).UTC()
		maxRuntime := time.Until(deadline) + 2*time.Minute
		if maxRuntime <= 0 || maxRuntime > 12*time.Minute {
			return errors.New("apply-update runtime window is outside policy")
		}
		ctx, cancel := context.WithTimeout(context.Background(), maxRuntime)
		defer cancel()
		action, err := app.ApplyUpdate(ctx, command)
		if err != nil {
			return err
		}
		log.Printf("IT Guardian update transaction completed: %s", action)
		return nil
	default:
		return errors.New("unsupported command")
	}
}
