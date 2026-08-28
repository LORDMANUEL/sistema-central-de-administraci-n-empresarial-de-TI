package spool

import (
	"encoding/json"
	"errors"
	"testing"
	"time"
)

func item(kind Kind, id string, n int) Item {
	return Item{Kind: kind, ID: id, Payload: json.RawMessage(`{"n":` + string(rune('0'+n)) + `}`), CreatedAt: time.Date(2026, 8, 28, 15, n, 0, 0, time.UTC)}
}

func TestQueuePersistsAcrossRestartAndDedupesStableID(t *testing.T) {
	dir := t.TempDir()
	q, err := New(dir, 1<<20, 10)
	if err != nil {
		t.Fatal(err)
	}
	first := item(KindTelemetry, "11111111-1111-4111-8111-111111111111", 1)
	if err := q.Enqueue(first); err != nil {
		t.Fatal(err)
	}
	if err := q.Enqueue(first); err != nil {
		t.Fatalf("idempotent enqueue: %v", err)
	}
	q2, err := New(dir, 1<<20, 10)
	if err != nil {
		t.Fatal(err)
	}
	items, err := q2.List()
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].ID != first.ID {
		t.Fatalf("items=%#v", items)
	}
	conflict := first
	conflict.Payload = json.RawMessage(`{"n":99}`)
	if err := q2.Enqueue(conflict); !errors.Is(err, ErrConflict) {
		t.Fatalf("expected conflict, got %v", err)
	}
	if err := q2.Ack(first.Kind, first.ID); err != nil {
		t.Fatal(err)
	}
	items, _ = q2.List()
	if len(items) != 0 {
		t.Fatalf("items after ack=%#v", items)
	}
}

func TestQueueEvictsOldTelemetryBeforeCommandResults(t *testing.T) {
	dir := t.TempDir()
	q, _ := New(dir, 1<<20, 2)
	telemetry := item(KindTelemetry, "11111111-1111-4111-8111-111111111111", 1)
	result1 := item(KindCommandResult, "22222222-2222-4222-8222-222222222222", 2)
	result2 := item(KindCommandResult, "33333333-3333-4333-8333-333333333333", 3)
	if err := q.Enqueue(telemetry); err != nil {
		t.Fatal(err)
	}
	if err := q.Enqueue(result1); err != nil {
		t.Fatal(err)
	}
	if err := q.Enqueue(result2); err != nil {
		t.Fatal(err)
	}
	items, err := q.List()
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 2 {
		t.Fatalf("items=%#v", items)
	}
	for _, it := range items {
		if it.Kind == KindTelemetry {
			t.Fatalf("telemetry should be evicted: %#v", items)
		}
	}
}

func TestQueueRefusesTelemetryWhenOnlyPriorityResultsFillCapacity(t *testing.T) {
	dir := t.TempDir()
	q, _ := New(dir, 1<<20, 1)
	if err := q.Enqueue(item(KindCommandResult, "11111111-1111-4111-8111-111111111111", 1)); err != nil {
		t.Fatal(err)
	}
	err := q.Enqueue(item(KindTelemetry, "22222222-2222-4222-8222-222222222222", 2))
	if !errors.Is(err, ErrFull) {
		t.Fatalf("expected ErrFull, got %v", err)
	}
	items, _ := q.List()
	if len(items) != 1 || items[0].Kind != KindCommandResult {
		t.Fatalf("priority item lost: %#v", items)
	}
}
