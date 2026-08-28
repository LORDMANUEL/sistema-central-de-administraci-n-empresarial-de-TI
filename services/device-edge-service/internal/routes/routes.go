package routes

import (
	"regexp"
	"strings"
)

type Target struct {
	Kind string
	Path string
}

var commandPath = regexp.MustCompile(`^/api/v1/device/commands/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/(running|result)$`)

func Match(method, path string) (Target, bool) {
	if strings.ToUpper(method) != "POST" {
		return Target{}, false
	}
	switch path {
	case "/api/v1/device/heartbeat":
		return Target{Kind: "agent-control", Path: path}, true
	case "/api/v1/device/commands/acquire":
		return Target{Kind: "command", Path: path}, true
	case "/api/v1/device/telemetry":
		return Target{Kind: "telemetry", Path: path}, true
	}
	if commandPath.MatchString(path) {
		return Target{Kind: "command", Path: path}, true
	}
	return Target{}, false
}
