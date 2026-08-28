package update

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

type Action string

const (
	ActionPending    Action = "pending"
	ActionCommitted  Action = "committed"
	ActionRolledBack Action = "rolled_back"
)

type Promotion struct {
	Current      string
	Staged       string
	Previous     string
	HealthMarker string
	Deadline     time.Time
}

func (p Promotion) validate() error {
	if p.Current == "" || p.Staged == "" || p.Previous == "" || p.HealthMarker == "" || p.Deadline.IsZero() {
		return errors.New("promotion paths/deadline are incomplete")
	}
	if p.Current == p.Staged || p.Current == p.Previous || p.Staged == p.Previous {
		return errors.New("promotion paths must be distinct")
	}
	if filepath.Dir(p.Current) != filepath.Dir(p.Staged) || filepath.Dir(p.Current) != filepath.Dir(p.Previous) {
		return errors.New("promotion binaries must be on the same filesystem directory")
	}
	return nil
}

func (p Promotion) Activate() error {
	if err := p.validate(); err != nil {
		return err
	}
	if _, err := os.Stat(p.Current); err != nil {
		return fmt.Errorf("current binary: %w", err)
	}
	if _, err := os.Stat(p.Staged); err != nil {
		return fmt.Errorf("staged binary: %w", err)
	}
	if _, err := os.Stat(p.Previous); err == nil {
		return errors.New("previous binary already exists; refusing to overwrite rollback state")
	} else if !os.IsNotExist(err) {
		return err
	}
	_ = os.Remove(p.HealthMarker)
	if err := os.Rename(p.Current, p.Previous); err != nil {
		return err
	}
	if err := os.Rename(p.Staged, p.Current); err != nil {
		_ = os.Rename(p.Previous, p.Current)
		return err
	}
	return syncDir(filepath.Dir(p.Current))
}

func (p Promotion) Evaluate(now time.Time) (Action, error) {
	if err := p.validate(); err != nil {
		return "", err
	}
	if _, err := os.Stat(p.HealthMarker); err == nil {
		if err := os.Remove(p.Previous); err != nil && !os.IsNotExist(err) {
			return "", err
		}
		_ = os.Remove(p.HealthMarker)
		if err := syncDir(filepath.Dir(p.Current)); err != nil {
			return "", err
		}
		return ActionCommitted, nil
	} else if !os.IsNotExist(err) {
		return "", err
	}
	if now.Before(p.Deadline) {
		return ActionPending, nil
	}
	if _, err := os.Stat(p.Previous); err != nil {
		return "", fmt.Errorf("rollback binary unavailable: %w", err)
	}
	failed := p.Staged + ".failed"
	_ = os.Remove(failed)
	if err := os.Rename(p.Current, failed); err != nil {
		return "", err
	}
	if err := os.Rename(p.Previous, p.Current); err != nil {
		_ = os.Rename(failed, p.Current)
		return "", err
	}
	if err := syncDir(filepath.Dir(p.Current)); err != nil {
		return "", err
	}
	return ActionRolledBack, nil
}

func syncDir(dir string) error {
	f, err := os.Open(dir)
	if err != nil {
		return err
	}
	defer f.Close()
	return f.Sync()
}
