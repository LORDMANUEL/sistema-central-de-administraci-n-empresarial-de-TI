//go:build windows

package telemetry

import (
	"context"
	"errors"
	"fmt"
	"syscall"
	"time"
	"unsafe"
)

const driveFixed = 3

type filetime struct {
	low  uint32
	high uint32
}

func (f filetime) uint64() uint64 { return uint64(f.high)<<32 | uint64(f.low) }

type memoryStatusEx struct {
	Length               uint32
	MemoryLoad           uint32
	TotalPhys            uint64
	AvailPhys            uint64
	TotalPageFile        uint64
	AvailPageFile        uint64
	TotalVirtual         uint64
	AvailVirtual         uint64
	AvailExtendedVirtual uint64
}

var (
	kernel32Telemetry        = syscall.NewLazyDLL("kernel32.dll")
	procGetSystemTimes       = kernel32Telemetry.NewProc("GetSystemTimes")
	procGlobalMemoryStatusEx = kernel32Telemetry.NewProc("GlobalMemoryStatusEx")
	procGetLogicalDrives     = kernel32Telemetry.NewProc("GetLogicalDrives")
	procGetDriveTypeW        = kernel32Telemetry.NewProc("GetDriveTypeW")
	procGetDiskFreeSpaceExW  = kernel32Telemetry.NewProc("GetDiskFreeSpaceExW")
)

func readCPUTimes() (cpuTimes, error) {
	var idle, kernel, user filetime
	r1, _, callErr := procGetSystemTimes.Call(uintptr(unsafe.Pointer(&idle)), uintptr(unsafe.Pointer(&kernel)), uintptr(unsafe.Pointer(&user)))
	if r1 == 0 {
		if callErr != syscall.Errno(0) {
			return cpuTimes{}, callErr
		}
		return cpuTimes{}, errors.New("GetSystemTimes failed")
	}
	return cpuTimes{idle: idle.uint64(), kernel: kernel.uint64(), user: user.uint64()}, nil
}

func memorySamples(observed time.Time) ([]Sample, error) {
	status := memoryStatusEx{Length: uint32(unsafe.Sizeof(memoryStatusEx{}))}
	r1, _, callErr := procGlobalMemoryStatusEx.Call(uintptr(unsafe.Pointer(&status)))
	if r1 == 0 {
		if callErr != syscall.Errno(0) {
			return nil, callErr
		}
		return nil, errors.New("GlobalMemoryStatusEx failed")
	}
	used := status.TotalPhys - status.AvailPhys
	return []Sample{
		{Metric: "memory.total_bytes", Value: status.TotalPhys, ObservedAt: observed},
		{Metric: "memory.used_bytes", Value: used, ObservedAt: observed},
	}, nil
}

func diskSamples(observed time.Time) ([]Sample, error) {
	mask, _, callErr := procGetLogicalDrives.Call()
	if mask == 0 {
		if callErr != syscall.Errno(0) {
			return nil, callErr
		}
		return nil, errors.New("GetLogicalDrives failed")
	}
	var samples []Sample
	for i := 0; i < 26; i++ {
		if mask&(1<<uint(i)) == 0 {
			continue
		}
		root := fmt.Sprintf("%c:\\", 'A'+i)
		rootPtr, err := syscall.UTF16PtrFromString(root)
		if err != nil {
			return nil, err
		}
		driveType, _, _ := procGetDriveTypeW.Call(uintptr(unsafe.Pointer(rootPtr)))
		if driveType != driveFixed {
			continue
		}
		var freeAvailable, total, totalFree uint64
		r1, _, spaceErr := procGetDiskFreeSpaceExW.Call(uintptr(unsafe.Pointer(rootPtr)), uintptr(unsafe.Pointer(&freeAvailable)), uintptr(unsafe.Pointer(&total)), uintptr(unsafe.Pointer(&totalFree)))
		if r1 == 0 {
			if spaceErr != syscall.Errno(0) {
				continue
			}
			continue
		}
		labels := map[string]string{"volume": root}
		samples = append(samples,
			Sample{Metric: "disk.total_bytes", Value: total, Labels: labels, ObservedAt: observed},
			Sample{Metric: "disk.free_bytes", Value: totalFree, Labels: labels, ObservedAt: observed},
		)
	}
	if len(samples) == 0 {
		return nil, errors.New("no fixed disk telemetry available")
	}
	return samples, nil
}

func Collect(ctx context.Context) ([]Sample, error) {
	previous, err := readCPUTimes()
	if err != nil {
		return nil, err
	}
	timer := time.NewTimer(250 * time.Millisecond)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	case <-timer.C:
	}
	current, err := readCPUTimes()
	if err != nil {
		return nil, err
	}
	cpu, err := cpuUtilization(previous, current)
	if err != nil {
		return nil, err
	}
	observed := time.Now().UTC()
	samples := []Sample{{Metric: "cpu.utilization_pct", Value: cpu, ObservedAt: observed}}
	memory, err := memorySamples(observed)
	if err != nil {
		return nil, err
	}
	samples = append(samples, memory...)
	disks, err := diskSamples(observed)
	if err != nil {
		return nil, err
	}
	samples = append(samples, disks...)
	for _, sample := range samples {
		if err := Validate(sample); err != nil {
			return nil, fmt.Errorf("collector emitted invalid %s: %w", sample.Metric, err)
		}
	}
	return samples, nil
}
