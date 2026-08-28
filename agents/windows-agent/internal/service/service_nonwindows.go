//go:build !windows

package service

import "errors"

const ServiceName = "ITGuardianAgent"

func IsWindowsService() (bool, error) { return false, nil }

func RunWindowsService(RunFunc) error {
	return errors.New("Windows Service Control Manager is unavailable on this platform")
}
