package heartbeat

import "time"

type Payload struct {
	SessionID         string    `json:"session_id"`
	AgentVersion      string    `json:"agent_version"`
	Platform          string    `json:"platform"`
	PlatformVersion   string    `json:"platform_version"`
	Capabilities      []string  `json:"capabilities"`
	CapabilityVersion int       `json:"capability_version"`
	SentAt            time.Time `json:"sent_at"`
}

var capabilities = []string{
	"heartbeat.v1",
	"telemetry.v1",
	"inventory.v1",
	"command.inventory_refresh.v1",
	"command.device_reboot.v1",
	"command.service_restart.v1",
	"spool.v1",
	"update.v1",
}

func Build(sessionID, agentVersion, platformVersion string, now time.Time) Payload {
	return Payload{
		SessionID: sessionID,
		AgentVersion: agentVersion,
		Platform: "windows",
		PlatformVersion: platformVersion,
		Capabilities: append([]string(nil), capabilities...),
		CapabilityVersion: 1,
		SentAt: now.UTC(),
	}
}

func ClampIntervals(heartbeatSeconds, commandSeconds int) (time.Duration, time.Duration) {
	heartbeat := time.Duration(heartbeatSeconds) * time.Second
	command := time.Duration(commandSeconds) * time.Second
	if heartbeat < 15*time.Second {
		heartbeat = 15 * time.Second
	}
	if heartbeat > 10*time.Minute {
		heartbeat = 10 * time.Minute
	}
	if command < 2*time.Second {
		command = 2 * time.Second
	}
	if command > 5*time.Minute {
		command = 5 * time.Minute
	}
	return heartbeat, command
}
