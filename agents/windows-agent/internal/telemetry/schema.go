package telemetry

import (
	"errors"
	"fmt"
	"math"
	"time"
)

type Sample struct {
	Metric     string            `json:"metric"`
	Value      any               `json:"value"`
	Labels     map[string]string `json:"labels,omitempty"`
	ObservedAt time.Time         `json:"observed_at"`
}

type Batch struct {
	BatchID string    `json:"batch_id"`
	SentAt  time.Time `json:"sent_at"`
	Samples []Sample  `json:"samples"`
}

var integerNonNegative = map[string]bool{
	"memory.used_bytes": true,
	"disk.free_bytes": true,
	"network.rx_bytes_total": true,
	"network.tx_bytes_total": true,
}
var integerPositive = map[string]bool{
	"memory.total_bytes": true,
	"disk.total_bytes": true,
}

func Validate(sample Sample) error {
	metric := sample.Metric
	if metric == "cpu.utilization_pct" {
		if len(sample.Labels) != 0 {
			return errors.New("cpu metric must not contain labels")
		}
		value, ok := numberFloat(sample.Value)
		if !ok || math.IsNaN(value) || math.IsInf(value, 0) || value < 0 || value > 100 {
			return errors.New("cpu utilization must be between 0 and 100")
		}
		return nil
	}
	positive, allowedPositive := integerPositive[metric]
	_, allowedNonNegative := integerNonNegative[metric]
	if !allowedPositive && !allowedNonNegative {
		return fmt.Errorf("unsupported metric: %s", metric)
	}
	value, ok := numberInt(sample.Value)
	if !ok {
		return errors.New("metric requires integer value")
	}
	if positive && value <= 0 {
		return errors.New("metric must be positive")
	}
	if !positive && value < 0 {
		return errors.New("metric must be non-negative")
	}
	if metric == "disk.free_bytes" || metric == "disk.total_bytes" {
		if len(sample.Labels) != 1 || sample.Labels["volume"] == "" {
			return errors.New("disk metric requires volume label")
		}
		if len(sample.Labels["volume"]) > 128 {
			return errors.New("volume label too long")
		}
	} else if len(sample.Labels) != 0 {
		return errors.New("metric must not contain labels")
	}
	return nil
}

func numberFloat(value any) (float64, bool) {
	switch v := value.(type) {
	case float64:
		return v, true
	case float32:
		return float64(v), true
	case int:
		return float64(v), true
	case int64:
		return float64(v), true
	default:
		return 0, false
	}
}

func numberInt(value any) (int64, bool) {
	switch v := value.(type) {
	case int:
		return int64(v), true
	case int64:
		return v, true
	case int32:
		return int64(v), true
	case uint64:
		if v > math.MaxInt64 {
			return 0, false
		}
		return int64(v), true
	case uint32:
		return int64(v), true
	default:
		return 0, false
	}
}
