package telemetry

import "testing"

func TestValidateSamplesMirrorsV06MetricContract(t *testing.T) {
	valid := []Sample{
		{Metric: "cpu.utilization_pct", Value: 42.5},
		{Metric: "memory.total_bytes", Value: int64(16 << 30)},
		{Metric: "memory.used_bytes", Value: int64(8 << 30)},
		{Metric: "disk.total_bytes", Value: int64(100 << 30), Labels: map[string]string{"volume": "C:\\"}},
		{Metric: "disk.free_bytes", Value: int64(25 << 30), Labels: map[string]string{"volume": "C:\\"}},
		{Metric: "network.rx_bytes_total", Value: int64(10)},
		{Metric: "network.tx_bytes_total", Value: int64(20)},
	}
	for _, sample := range valid {
		if err := Validate(sample); err != nil {
			t.Fatalf("%s: %v", sample.Metric, err)
		}
	}

	invalid := []Sample{
		{Metric: "cpu.temperature", Value: 50},
		{Metric: "cpu.utilization_pct", Value: 101.0},
		{Metric: "memory.total_bytes", Value: int64(0)},
		{Metric: "memory.used_bytes", Value: int64(-1)},
		{Metric: "disk.free_bytes", Value: int64(1)},
		{Metric: "network.rx_bytes_total", Value: int64(1), Labels: map[string]string{"iface": "eth0"}},
	}
	for _, sample := range invalid {
		if err := Validate(sample); err == nil {
			t.Fatalf("expected invalid sample: %#v", sample)
		}
	}
}
