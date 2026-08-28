//go:build !windows

package app

import (
	"context"
	"errors"

	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/config"
	agentupdate "github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/update"
)

func PrepareUpdate(context.Context, config.Runtime, string) (string, error) {
	return "", errors.New("agent update application is supported only on Windows")
}

func ApplyUpdate(context.Context, Command) (agentupdate.Action, error) {
	return "", errors.New("agent update application is supported only on Windows")
}
