package service

import (
	"context"
	"errors"
	"testing"
)

func TestRunForegroundExecutesWorkerAndPropagatesError(t *testing.T) {
	want := errors.New("worker failed")
	err := RunForeground(context.Background(), func(context.Context) error { return want })
	if !errors.Is(err, want) {
		t.Fatalf("err=%v", err)
	}
}

func TestRunForegroundRequiresWorker(t *testing.T) {
	if err := RunForeground(context.Background(), nil); err == nil {
		t.Fatal("expected missing worker error")
	}
}
