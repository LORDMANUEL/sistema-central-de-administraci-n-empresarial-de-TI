//go:build windows

package keystore

import (
	"errors"
	"syscall"
	"unsafe"
)

const (
	cryptprotectUIForbidden  = 0x1
	cryptprotectLocalMachine = 0x4
)

type dataBlob struct {
	cbData uint32
	pbData *byte
}

var (
	crypt32                 = syscall.NewLazyDLL("crypt32.dll")
	kernel32                = syscall.NewLazyDLL("kernel32.dll")
	procCryptProtectData    = crypt32.NewProc("CryptProtectData")
	procCryptUnprotectData  = crypt32.NewProc("CryptUnprotectData")
	procLocalFree           = kernel32.NewProc("LocalFree")
)

func blob(data []byte) dataBlob {
	if len(data) == 0 {
		return dataBlob{}
	}
	return dataBlob{cbData: uint32(len(data)), pbData: &data[0]}
}

func bytesFromBlob(out *dataBlob) []byte {
	if out == nil || out.cbData == 0 || out.pbData == nil {
		return nil
	}
	view := unsafe.Slice(out.pbData, int(out.cbData))
	result := append([]byte(nil), view...)
	_, _, _ = procLocalFree.Call(uintptr(unsafe.Pointer(out.pbData)))
	return result
}

func Protect(data []byte) ([]byte, error) {
	if len(data) == 0 {
		return nil, errors.New("private key data is empty")
	}
	in := blob(data)
	var out dataBlob
	r1, _, callErr := procCryptProtectData.Call(
		uintptr(unsafe.Pointer(&in)), 0, 0, 0, 0,
		cryptprotectUIForbidden|cryptprotectLocalMachine,
		uintptr(unsafe.Pointer(&out)),
	)
	if r1 == 0 {
		if callErr != syscall.Errno(0) {
			return nil, callErr
		}
		return nil, errors.New("CryptProtectData failed")
	}
	return bytesFromBlob(&out), nil
}

func Unprotect(data []byte) ([]byte, error) {
	if len(data) == 0 {
		return nil, errors.New("protected private key data is empty")
	}
	in := blob(data)
	var out dataBlob
	r1, _, callErr := procCryptUnprotectData.Call(
		uintptr(unsafe.Pointer(&in)), 0, 0, 0, 0,
		cryptprotectUIForbidden,
		uintptr(unsafe.Pointer(&out)),
	)
	if r1 == 0 {
		if callErr != syscall.Errno(0) {
			return nil, callErr
		}
		return nil, errors.New("CryptUnprotectData failed")
	}
	return bytesFromBlob(&out), nil
}
