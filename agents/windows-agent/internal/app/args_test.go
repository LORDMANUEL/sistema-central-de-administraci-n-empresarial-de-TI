package app

import "testing"

func TestParseVersionAndRunCommands(t *testing.T) {
	cmd, err := ParseArgs([]string{"version"})
	if err != nil || cmd.Kind != CommandVersion {
		t.Fatalf("cmd=%#v err=%v", cmd, err)
	}
	cmd, err = ParseArgs([]string{"run", "--config", `C:\ProgramData\ITGuardian\Agent\agent.json`})
	if err != nil || cmd.Kind != CommandRun || cmd.ConfigPath == "" {
		t.Fatalf("cmd=%#v err=%v", cmd, err)
	}
}

func TestParseEnrollRequiresGatewayAndToken(t *testing.T) {
	if _, err := ParseArgs([]string{"enroll", "--gateway", "https://guardian.example"}); err == nil {
		t.Fatal("expected missing token error")
	}
	cmd, err := ParseArgs([]string{"enroll", "--gateway", "https://guardian.example", "--token", "one-time-token", "--state", `C:\ProgramData\ITGuardian\Agent\identity.json`, "--hostname", "PC-01"})
	if err != nil {
		t.Fatal(err)
	}
	if cmd.Kind != CommandEnroll || cmd.EnrollmentToken != "one-time-token" || cmd.Hostname != "PC-01" {
		t.Fatalf("cmd=%#v", cmd)
	}
}

func TestParseRejectsUnknownCommandsAndTrailingArguments(t *testing.T) {
	if _, err := ParseArgs([]string{"shell"}); err == nil {
		t.Fatal("expected unknown command rejection")
	}
	if _, err := ParseArgs([]string{"run", "unexpected"}); err == nil {
		t.Fatal("expected trailing argument rejection")
	}
}
