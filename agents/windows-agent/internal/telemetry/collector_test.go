package telemetry

import (
	"math"
	"testing"
)

func TestCPUUtilizationUsesKernelUserMinusIdle(t *testing.T) {
	prev := cpuTimes{idle: 100, kernel: 300, user: 200}
	next := cpuTimes{idle: 150, kernel: 450, user: 300}
	got, err := cpuUtilization(prev, next)
	if err != nil {
		t.Fatal(err)
	}
	if math.Abs(got-80) > 0.001 {
		t.Fatalf("utilization=%f", got)
	}
}

func TestCPUUtilizationRejectsNonMonotonicCounters(t *testing.T) {
	if _, err := cpuUtilization(cpuTimes{idle: 10, kernel: 20, user: 20}, cpuTimes{idle: 5, kernel: 25, user: 25}); err == nil {
		t.Fatal("expected non-monotonic error")
	}
	if _, err := cpuUtilization(cpuTimes{idle: 10, kernel: 20, user: 20}, cpuTimes{idle: 10, kernel: 20, user: 20}); err == nil {
		t.Fatal("expected zero-delta error")
	}
}
