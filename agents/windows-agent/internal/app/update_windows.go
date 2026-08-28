//go:build windows

package app

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/config"
	agentservice "github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/service"
	agentupdate "github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/update"
)

func PrepareUpdate(ctx context.Context, cfg config.Runtime, currentVersion string) (string, error) {
	if err := cfg.Validate(); err != nil {
		return "", err
	}
	if !cfg.UpdateEnabled() {
		return "", errors.New("signed update catalog is not configured")
	}
	publicKey, err := cfg.UpdatePublicKeyBytes()
	if err != nil {
		return "", err
	}
	current, err := os.Executable()
	if err != nil {
		return "", err
	}
	current, err = filepath.Abs(current)
	if err != nil {
		return "", err
	}
	paths, err := buildUpdatePaths(current, cfg.StatePath)
	if err != nil {
		return "", err
	}
	if _, err := os.Stat(paths.Previous); err == nil {
		return "", errors.New("previous update rollback state exists; refusing a new update")
	} else if !os.IsNotExist(err) {
		return "", err
	}

	httpClient := &http.Client{Timeout: 5 * time.Minute}
	manifest, err := agentupdate.Stage(httpClient, cfg.UpdateManifestURL, publicKey, currentVersion, paths.Staged, cfg.UpdateMaxBytes)
	if err != nil {
		return "", err
	}
	if err := copyExecutableAtomic(current, paths.Helper); err != nil {
		_ = os.Remove(paths.Staged)
		return "", fmt.Errorf("prepare update helper: %w", err)
	}
	deadline := time.Now().UTC().Add(time.Duration(cfg.UpdateHealthTimeoutSeconds) * time.Second)
	args := []string{
		"apply-update",
		"--parent-pid", strconv.Itoa(os.Getpid()),
		"--current", current,
		"--staged", paths.Staged,
		"--previous", paths.Previous,
		"--health", paths.Health,
		"--deadline-unix", strconv.FormatInt(deadline.Unix(), 10),
	}
	command := exec.CommandContext(ctx, paths.Helper, args...)
	command.Stdin = nil
	command.Stdout = nil
	command.Stderr = nil
	if err := command.Start(); err != nil {
		_ = os.Remove(paths.Staged)
		_ = os.Remove(paths.Helper)
		return "", fmt.Errorf("launch update helper: %w", err)
	}
	if err := command.Process.Release(); err != nil {
		return "", fmt.Errorf("release update helper: %w", err)
	}
	return manifest.Version, nil
}

func ApplyUpdate(ctx context.Context, command Command) (agentupdate.Action, error) {
	if command.Kind != CommandApplyUpdate {
		return "", errors.New("apply-update command is required")
	}
	helperPath, err := os.Executable()
	if err != nil {
		return "", err
	}
	helperPath, err = filepath.Abs(helperPath)
	if err != nil {
		return "", err
	}
	currentPath, err := filepath.Abs(command.CurrentPath)
	if err != nil {
		return "", err
	}
	expectedHelper := currentPath + ".update-helper"
	if !strings.EqualFold(filepath.Clean(helperPath), filepath.Clean(expectedHelper)) {
		return "", errors.New("apply-update may run only from the generated update helper copy")
	}
	deadline := time.Unix(command.DeadlineUnix, 0).UTC()
	now := time.Now().UTC()
	if !deadline.After(now) || deadline.After(now.Add(10*time.Minute)) {
		return "", errors.New("apply-update deadline is outside policy")
	}
	promotion := agentupdate.Promotion{
		Current: currentPath,
		Staged: command.StagedPath,
		Previous: command.PreviousPath,
		HealthMarker: command.HealthPath,
		Deadline: deadline,
	}
	controller := agentupdate.WindowsServiceController{Name: agentservice.ServiceName, Timeout: 30 * time.Second}
	return agentupdate.FinalizeUpdate(ctx, promotion, controller, command.ParentPID, agentupdate.WaitParentExit, 500*time.Millisecond)
}

func copyExecutableAtomic(source, destination string) error {
	if strings.EqualFold(filepath.Clean(source), filepath.Clean(destination)) {
		return errors.New("update helper source/destination must differ")
	}
	if err := os.Remove(destination); err != nil && !os.IsNotExist(err) {
		return err
	}
	in, err := os.Open(source)
	if err != nil {
		return err
	}
	defer in.Close()
	if err := os.MkdirAll(filepath.Dir(destination), 0o755); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(destination), ".update-helper-*")
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()
	ok := false
	defer func() {
		_ = tmp.Close()
		if !ok {
			_ = os.Remove(tmpPath)
		}
	}()
	if err := tmp.Chmod(0o700); err != nil {
		return err
	}
	if _, err := io.Copy(tmp, io.LimitReader(in, 256<<20)); err != nil {
		return err
	}
	if err := tmp.Sync(); err != nil {
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmpPath, destination); err != nil {
		return err
	}
	ok = true
	return nil
}
