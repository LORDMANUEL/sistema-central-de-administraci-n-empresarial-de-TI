//go:build !windows

package commands

import (
	"context"
	"errors"
)

type NativePlatform struct {
	Refresh func(context.Context) error
}

func (p NativePlatform) RefreshInventory(ctx context.Context) error {
	if p.Refresh != nil {
		return p.Refresh(ctx)
	}
	return nil
}

func (NativePlatform) Reboot(int) error {
	return errors.New("Windows reboot API is unavailable on this platform")
}

func (NativePlatform) RestartService(string) error {
	return errors.New("Windows SCM is unavailable on this platform")
}
