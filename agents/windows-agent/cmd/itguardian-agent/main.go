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
	default:
		return errors.New("unsupported command")
	}
}
