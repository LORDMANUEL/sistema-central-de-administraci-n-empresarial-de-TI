package app

import (
	"path/filepath"
	"testing"
)

func TestUpdateTransactionPathsKeepBinariesTogetherAndHealthWithState(t *testing.T) {
	current := filepath.Join("C:", "Program Files", "IT Guardian", "itguardian-agent.exe")
	statePath := filepath.Join("C:", "ProgramData", "ITGuardian", "Agent", "identity.json")
	paths, err := buildUpdatePaths(current, statePath)
	if err != nil {
		t.Fatal(err)
	}
	if paths.Staged != current+".staged" || paths.Previous != current+".previous" || paths.Helper != current+".update-helper" {
		t.Fatalf("binary paths=%#v", paths)
	}
	if paths.Health != filepath.Join(filepath.Dir(statePath), "update-healthy") {
		t.Fatalf("health=%q", paths.Health)
	}
}

func TestUpdateTransactionPathsRejectEmptyOrNonExecutableCurrent(t *testing.T) {
	if _, err := buildUpdatePaths("", "identity.json"); err == nil {
		t.Fatal("expected empty current rejection")
	}
	if _, err := buildUpdatePaths("agent.txt", "identity.json"); err == nil {
		t.Fatal("expected non-executable current rejection")
	}
}
