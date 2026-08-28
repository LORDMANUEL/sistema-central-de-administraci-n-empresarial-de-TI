//go:build windows

package update

import (
	"context"
	"errors"
	"fmt"
	"time"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/svc"
	"golang.org/x/sys/windows/svc/mgr"
)

type WindowsServiceController struct {
	Name    string
	Timeout time.Duration
}

func (c WindowsServiceController) normalized() (string, time.Duration, error) {
	if c.Name == "" {
		return "", 0, errors.New("Windows service name is required")
	}
	timeout := c.Timeout
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	if timeout > 2*time.Minute {
		return "", 0, errors.New("Windows service timeout exceeds policy")
	}
	return c.Name, timeout, nil
}

func (c WindowsServiceController) Stop(ctx context.Context) error {
	name, timeout, err := c.normalized()
	if err != nil {
		return err
	}
	manager, err := mgr.Connect()
	if err != nil {
		return err
	}
	defer manager.Disconnect()
	service, err := manager.OpenService(name)
	if err != nil {
		return err
	}
	defer service.Close()
	status, err := service.Query()
	if err != nil {
		return err
	}
	if status.State == svc.Stopped {
		return nil
	}
	if _, err := service.Control(svc.Stop); err != nil && !errors.Is(err, windows.ERROR_SERVICE_NOT_ACTIVE) {
		return err
	}
	deadline := time.Now().Add(timeout)
	for {
		status, err = service.Query()
		if err != nil {
			return err
		}
		if status.State == svc.Stopped {
			return nil
		}
		if time.Now().After(deadline) {
			return errors.New("Windows service stop timed out")
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(250 * time.Millisecond):
		}
	}
}

func (c WindowsServiceController) Start() error {
	name, timeout, err := c.normalized()
	if err != nil {
		return err
	}
	manager, err := mgr.Connect()
	if err != nil {
		return err
	}
	defer manager.Disconnect()
	service, err := manager.OpenService(name)
	if err != nil {
		return err
	}
	defer service.Close()
	status, err := service.Query()
	if err != nil {
		return err
	}
	if status.State == svc.Running {
		return nil
	}
	if err := service.Start(); err != nil {
		return err
	}
	deadline := time.Now().Add(timeout)
	for {
		status, err = service.Query()
		if err != nil {
			return err
		}
		if status.State == svc.Running {
			return nil
		}
		if status.State == svc.Stopped {
			return fmt.Errorf("Windows service stopped during startup: win32=%d service=%d", status.Win32ExitCode, status.ServiceSpecificExitCode)
		}
		if time.Now().After(deadline) {
			return errors.New("Windows service start timed out")
		}
		time.Sleep(250 * time.Millisecond)
	}
}

func WaitParentExit(ctx context.Context, pid int) error {
	if pid <= 0 {
		return errors.New("parent PID must be positive")
	}
	handle, err := windows.OpenProcess(windows.SYNCHRONIZE, false, uint32(pid))
	if errors.Is(err, windows.ERROR_INVALID_PARAMETER) {
		return nil
	}
	if err != nil {
		return err
	}
	defer windows.CloseHandle(handle)
	for {
		result, err := windows.WaitForSingleObject(handle, 500)
		if err != nil {
			return err
		}
		switch result {
		case windows.WAIT_OBJECT_0:
			return nil
		case uint32(windows.WAIT_TIMEOUT):
			select {
			case <-ctx.Done():
				return ctx.Err()
			default:
			}
		default:
			return fmt.Errorf("unexpected WaitForSingleObject result: %d", result)
		}
	}
}
