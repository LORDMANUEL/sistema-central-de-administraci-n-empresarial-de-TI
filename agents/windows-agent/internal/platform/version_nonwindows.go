//go:build !windows

package platform

import "runtime"

func Version() (string, error) {
	return runtime.GOOS + "/" + runtime.GOARCH, nil
}
