package update

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func writeUpdateTestFile(t *testing.T, path, value string) {
	t.Helper()
	if err := os.WriteFile(path, []byte(value), 0o600); err != nil {
		t.Fatal(err)
	}
}

func readUpdateTestFile(t *testing.T, path string) string {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return string(b)
}

func TestPromotionCommitsAfterHealthMarker(t *testing.T) {
	d := t.TempDir()
	current := filepath.Join(d, "agent.exe")
	staged := filepath.Join(d, "agent.new.exe")
	previous := filepath.Join(d, "agent.previous.exe")
	marker := filepath.Join(d, "healthy")
	writeUpdateTestFile(t, current, "old")
	writeUpdateTestFile(t, staged, "new")
	p := Promotion{Current: current, Staged: staged, Previous: previous, HealthMarker: marker, Deadline: time.Now().Add(time.Minute)}
	if err := p.Activate(); err != nil {
		t.Fatal(err)
	}
	if readUpdateTestFile(t, current) != "new" || readUpdateTestFile(t, previous) != "old" {
		t.Fatal("activation did not preserve previous binary")
	}
	writeUpdateTestFile(t, marker, "ok")
	action, err := p.Evaluate(time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if action != ActionCommitted {
		t.Fatalf("action=%s", action)
	}
	if _, err := os.Stat(previous); !os.IsNotExist(err) {
		t.Fatalf("previous still exists: %v", err)
	}
}

func TestPromotionRollsBackAfterHealthTimeout(t *testing.T) {
	d := t.TempDir()
	current := filepath.Join(d, "agent.exe")
	staged := filepath.Join(d, "agent.new.exe")
	previous := filepath.Join(d, "agent.previous.exe")
	marker := filepath.Join(d, "healthy")
	writeUpdateTestFile(t, current, "old")
	writeUpdateTestFile(t, staged, "broken")
	deadline := time.Now().Add(-time.Second)
	p := Promotion{Current: current, Staged: staged, Previous: previous, HealthMarker: marker, Deadline: deadline}
	if err := p.Activate(); err != nil {
		t.Fatal(err)
	}
	action, err := p.Evaluate(time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if action != ActionRolledBack {
		t.Fatalf("action=%s", action)
	}
	if readUpdateTestFile(t, current) != "old" {
		t.Fatal("previous binary was not restored")
	}
}
