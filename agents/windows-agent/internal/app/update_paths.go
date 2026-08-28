package app

import (
	"errors"
	"path/filepath"
	"strings"
)

type updatePaths struct {
	Staged   string
	Previous string
	Helper   string
	Health   string
}

func buildUpdatePaths(current, statePath string) (updatePaths, error) {
	current = strings.TrimSpace(current)
	statePath = strings.TrimSpace(statePath)
	if current == "" || statePath == "" {
		return updatePaths{}, errors.New("update current/state paths are required")
	}
	if strings.ToLower(filepath.Ext(current)) != ".exe" {
		return updatePaths{}, errors.New("update current path must be a Windows executable")
	}
	return updatePaths{
		Staged:   current + ".staged",
		Previous: current + ".previous",
		Helper:   current + ".update-helper",
		Health:   filepath.Join(filepath.Dir(statePath), "update-healthy"),
	}, nil
}
