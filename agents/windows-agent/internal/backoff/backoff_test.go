package backoff

import (
	"testing"
	"time"
)

func TestExponentialBackoffCapsAndResets(t *testing.T) {
	b := New(time.Second, 5*time.Minute, func() float64 { return 0.5 })
	if got := b.Next(); got != time.Second {
		t.Fatalf("first=%s", got)
	}
	if got := b.Next(); got != 2*time.Second {
		t.Fatalf("second=%s", got)
	}
	for i := 0; i < 20; i++ {
		_ = b.Next()
	}
	if got := b.Next(); got != 5*time.Minute {
		t.Fatalf("cap=%s", got)
	}
	b.Reset()
	if got := b.Next(); got != time.Second {
		t.Fatalf("reset=%s", got)
	}
}

func TestBackoffJitterStaysWithinHalfToOneAndHalf(t *testing.T) {
	low := New(10*time.Second, time.Minute, func() float64 { return 0 })
	high := New(10*time.Second, time.Minute, func() float64 { return 1 })
	if got := low.Next(); got != 5*time.Second {
		t.Fatalf("low=%s", got)
	}
	if got := high.Next(); got != 15*time.Second {
		t.Fatalf("high=%s", got)
	}
}
