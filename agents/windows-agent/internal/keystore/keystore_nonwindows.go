//go:build !windows

package keystore

import "errors"

var ErrDPAPIUnavailable = errors.New("DPAPI is available only on Windows")

func Protect(data []byte) ([]byte, error) {
	return nil, ErrDPAPIUnavailable
}

func Unprotect(data []byte) ([]byte, error) {
	return nil, ErrDPAPIUnavailable
}
