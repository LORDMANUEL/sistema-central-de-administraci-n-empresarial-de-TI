package telemetry

import "errors"

type cpuTimes struct {
	idle   uint64
	kernel uint64
	user   uint64
}

func cpuUtilization(previous, current cpuTimes) (float64, error) {
	if current.idle < previous.idle || current.kernel < previous.kernel || current.user < previous.user {
		return 0, errors.New("CPU counters are not monotonic")
	}
	idle := current.idle - previous.idle
	kernel := current.kernel - previous.kernel
	user := current.user - previous.user
	total := kernel + user
	if total == 0 || idle > total {
		return 0, errors.New("CPU counter delta is invalid")
	}
	return float64(total-idle) * 100 / float64(total), nil
}
