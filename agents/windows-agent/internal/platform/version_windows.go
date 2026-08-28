//go:build windows

package platform

import (
	"errors"
	"fmt"
	"syscall"
	"unsafe"
)

type osVersionInfo struct {
	Size             uint32
	MajorVersion     uint32
	MinorVersion     uint32
	BuildNumber      uint32
	PlatformID       uint32
	CSDVersion       [128]uint16
	ServicePackMajor uint16
	ServicePackMinor uint16
	SuiteMask        uint16
	ProductType      byte
	Reserved         byte
}

var rtlGetVersion = syscall.NewLazyDLL("ntdll.dll").NewProc("RtlGetVersion")

func Version() (string, error) {
	info := osVersionInfo{Size: uint32(unsafe.Sizeof(osVersionInfo{}))}
	status, _, _ := rtlGetVersion.Call(uintptr(unsafe.Pointer(&info)))
	if status != 0 {
		return "", errors.New("RtlGetVersion failed")
	}
	return fmt.Sprintf("%d.%d.%d", info.MajorVersion, info.MinorVersion, info.BuildNumber), nil
}
