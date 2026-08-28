package update

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"
)

type fakeService struct {
	stops  int
	starts int
	onStart func() error
}

func (f *fakeService) Stop(context.Context) error { f.stops++; return nil }
func (f *fakeService) Start() error {
	f.starts++
	if f.onStart != nil {
		return f.onStart()
	}
	return nil
}

func updateFiles(t *testing.T, deadline time.Time) Promotion {
	t.Helper()
	dir := t.TempDir()
	current := filepath.Join(dir, "agent.exe")
	staged := filepath.Join(dir, "agent.exe.staged")
	previous := filepath.Join(dir, "agent.exe.previous")
	health := filepath.Join(dir, "update-healthy")
	if err := os.WriteFile(current, []byte("old"), 0o700); err != nil { t.Fatal(err) }
	if err := os.WriteFile(staged, []byte("new"), 0o700); err != nil { t.Fatal(err) }
	return Promotion{Current: current, Staged: staged, Previous: previous, HealthMarker: health, Deadline: deadline}
}

func TestFinalizeUpdateCommitsOnlyAfterHealthMarker(t *testing.T) {
	promotion := updateFiles(t, time.Now().Add(time.Second))
	service := &fakeService{}
	waited := false
	service.onStart = func() error {
		return os.WriteFile(promotion.HealthMarker, []byte("ok"), 0o600)
	}
	action, err := FinalizeUpdate(
		context.Background(), promotion, service, 123,
		func(context.Context, int) error { waited = true; return nil },
		5*time.Millisecond,
	)
	if err != nil { t.Fatal(err) }
	if action != ActionCommitted || !waited || service.stops != 1 || service.starts != 1 {
		t.Fatalf("action=%s waited=%v stops=%d starts=%d", action, waited, service.stops, service.starts)
	}
	current, _ := os.ReadFile(promotion.Current)
	if string(current) != "new" { t.Fatalf("current=%q", current) }
	if _, err := os.Stat(promotion.Previous); !os.IsNotExist(err) { t.Fatal("previous should be removed after commit") }
}

func TestFinalizeUpdateRollsBackAndRestartsPreviousOnHealthTimeout(t *testing.T) {
	promotion := updateFiles(t, time.Now().Add(25*time.Millisecond))
	service := &fakeService{}
	action, err := FinalizeUpdate(
		context.Background(), promotion, service, 123,
		func(context.Context, int) error { return nil },
		5*time.Millisecond,
	)
	if err != nil { t.Fatal(err) }
	if action != ActionRolledBack || service.stops != 2 || service.starts != 2 {
		t.Fatalf("action=%s stops=%d starts=%d", action, service.stops, service.starts)
	}
	current, _ := os.ReadFile(promotion.Current)
	if string(current) != "old" { t.Fatalf("current=%q", current) }
}

func TestFinalizeUpdateDoesNotActivateWhenParentWaitFails(t *testing.T) {
	promotion := updateFiles(t, time.Now().Add(time.Second))
	service := &fakeService{}
	want := errors.New("parent wait failed")
	_, err := FinalizeUpdate(
		context.Background(), promotion, service, 123,
		func(context.Context, int) error { return want },
		5*time.Millisecond,
	)
	if !errors.Is(err, want) { t.Fatalf("err=%v", err) }
	if service.stops != 0 || service.starts != 0 { t.Fatalf("service touched: %#v", service) }
	current, _ := os.ReadFile(promotion.Current)
	if string(current) != "old" { t.Fatalf("current changed=%q", current) }
}
