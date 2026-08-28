package service

import (
	"context"
	"errors"
)

type RunFunc func(context.Context) error

func RunForeground(ctx context.Context, run RunFunc) error {
	if run == nil {
		return errors.New("service worker is required")
	}
	return run(ctx)
}
