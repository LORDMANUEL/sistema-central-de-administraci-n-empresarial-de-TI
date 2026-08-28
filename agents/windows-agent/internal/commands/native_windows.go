//go:build windows

package commands

import (
	"context"
	"errors"
	"fmt"
	"syscall"
	"time"
	"unsafe"
)

const (
	scManagerConnect    = 0x0001
	serviceQueryStatus  = 0x0004
	serviceStart        = 0x0010
	serviceStop         = 0x0020
	serviceControlStop  = 0x00000001
	serviceStopped      = 0x00000001
	serviceStopPending  = 0x00000003
)

type serviceStatus struct {
	ServiceType             uint32
	CurrentState            uint32
	ControlsAccepted        uint32
	Win32ExitCode           uint32
	ServiceSpecificExitCode uint32
	CheckPoint              uint32
	WaitHint                uint32
}

var (
	advapi32                       = syscall.NewLazyDLL("advapi32.dll")
	procInitiateSystemShutdownExW  = advapi32.NewProc("InitiateSystemShutdownExW")
	procOpenSCManagerW             = advapi32.NewProc("OpenSCManagerW")
	procOpenServiceW               = advapi32.NewProc("OpenServiceW")
	procControlService             = advapi32.NewProc("ControlService")
	procQueryServiceStatus         = advapi32.NewProc("QueryServiceStatus")
	procStartServiceW              = advapi32.NewProc("StartServiceW")
	procCloseServiceHandle         = advapi32.NewProc("CloseServiceHandle")
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

func (NativePlatform) Reboot(delaySeconds int) error {
	if delaySeconds < 0 || delaySeconds > 3600 {
		return errors.New("reboot delay outside policy")
	}
	r1, _, callErr := procInitiateSystemShutdownExW.Call(0, 0, uintptr(uint32(delaySeconds)), 0, 1, 0x80000000)
	if r1 == 0 {
		if callErr != syscall.Errno(0) {
			return callErr
		}
		return errors.New("InitiateSystemShutdownExW failed")
	}
	return nil
}

func (NativePlatform) RestartService(name string) error {
	namePtr, err := syscall.UTF16PtrFromString(name)
	if err != nil {
		return err
	}
	scm, _, callErr := procOpenSCManagerW.Call(0, 0, scManagerConnect)
	if scm == 0 {
		if callErr != syscall.Errno(0) {
			return callErr
		}
		return errors.New("OpenSCManagerW failed")
	}
	defer procCloseServiceHandle.Call(scm)
	handle, _, callErr := procOpenServiceW.Call(scm, uintptr(unsafe.Pointer(namePtr)), serviceQueryStatus|serviceStart|serviceStop)
	if handle == 0 {
		if callErr != syscall.Errno(0) {
			return callErr
		}
		return errors.New("OpenServiceW failed")
	}
	defer procCloseServiceHandle.Call(handle)

	var status serviceStatus
	r1, _, stopErr := procControlService.Call(handle, serviceControlStop, uintptr(unsafe.Pointer(&status)))
	if r1 == 0 && stopErr != syscall.Errno(1062) && stopErr != syscall.Errno(0) {
		return fmt.Errorf("stop service: %w", stopErr)
	}
	deadline := time.Now().Add(30 * time.Second)
	for {
		r1, _, queryErr := procQueryServiceStatus.Call(handle, uintptr(unsafe.Pointer(&status)))
		if r1 == 0 {
			if queryErr != syscall.Errno(0) {
				return queryErr
			}
			return errors.New("QueryServiceStatus failed")
		}
		if status.CurrentState == serviceStopped {
			break
		}
		if status.CurrentState != serviceStopPending || time.Now().After(deadline) {
			return errors.New("service did not stop within timeout")
		}
		time.Sleep(250 * time.Millisecond)
	}
	r1, _, startErr := procStartServiceW.Call(handle, 0, 0)
	if r1 == 0 {
		if startErr != syscall.Errno(0) {
			return fmt.Errorf("start service: %w", startErr)
		}
		return errors.New("StartServiceW failed")
	}
	return nil
}
