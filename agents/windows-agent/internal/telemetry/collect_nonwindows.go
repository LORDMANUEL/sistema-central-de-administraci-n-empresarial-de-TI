//go:build !windows

package telemetry

import (
	"context"
	"errors"
)

func Collect(context.Context) ([]Sample, error) {
	return nil, errors.New("Windows telemetry collector is unavailable on this platform")
}
