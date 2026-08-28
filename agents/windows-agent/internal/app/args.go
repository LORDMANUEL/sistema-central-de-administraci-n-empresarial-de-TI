package app

import (
	"errors"
	"flag"
	"io"
	"os"
	"strconv"
	"strings"

	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/config"
)

type CommandKind string

const (
	CommandVersion     CommandKind = "version"
	CommandEnroll      CommandKind = "enroll"
	CommandRun         CommandKind = "run"
	CommandUpdate      CommandKind = "update"
	CommandApplyUpdate CommandKind = "apply-update"
)

type Command struct {
	Kind            CommandKind
	ConfigPath      string
	GatewayURL      string
	EnrollmentToken string
	StatePath       string
	Hostname        string
	ParentPID       int
	CurrentPath     string
	StagedPath      string
	PreviousPath    string
	HealthPath      string
	DeadlineUnix    int64
}

func ParseArgs(args []string) (Command, error) {
	if len(args) == 0 {
		return Command{}, errors.New("command is required: version, enroll, run or update")
	}
	switch args[0] {
	case string(CommandVersion):
		if len(args) != 1 {
			return Command{}, errors.New("version accepts no arguments")
		}
		return Command{Kind: CommandVersion}, nil
	case string(CommandRun), string(CommandUpdate):
		kind := CommandKind(args[0])
		fs := flag.NewFlagSet(args[0], flag.ContinueOnError)
		fs.SetOutput(io.Discard)
		cfg := fs.String("config", "", "runtime config path")
		if err := fs.Parse(args[1:]); err != nil {
			return Command{}, err
		}
		if fs.NArg() != 0 {
			return Command{}, errors.New(args[0] + " accepts no positional arguments")
		}
		path := strings.TrimSpace(*cfg)
		if path == "" {
			path = config.DefaultDataDir() + string(os.PathSeparator) + "agent.json"
		}
		return Command{Kind: kind, ConfigPath: path}, nil
	case string(CommandEnroll):
		fs := flag.NewFlagSet("enroll", flag.ContinueOnError)
		fs.SetOutput(io.Discard)
		gateway := fs.String("gateway", "", "Gateway base URL")
		token := fs.String("token", "", "one-time enrollment token")
		statePath := fs.String("state", "", "identity state path")
		hostname := fs.String("hostname", "", "device hostname")
		if err := fs.Parse(args[1:]); err != nil {
			return Command{}, err
		}
		if fs.NArg() != 0 {
			return Command{}, errors.New("enroll accepts no positional arguments")
		}
		if strings.TrimSpace(*gateway) == "" || strings.TrimSpace(*token) == "" {
			return Command{}, errors.New("enroll requires --gateway and --token")
		}
		path := strings.TrimSpace(*statePath)
		if path == "" {
			path = config.DefaultDataDir() + string(os.PathSeparator) + "identity.json"
		}
		host := strings.TrimSpace(*hostname)
		if host == "" {
			resolved, err := os.Hostname()
			if err != nil || strings.TrimSpace(resolved) == "" {
				return Command{}, errors.New("hostname could not be determined; pass --hostname")
			}
			host = resolved
		}
		return Command{Kind: CommandEnroll, GatewayURL: strings.TrimSpace(*gateway), EnrollmentToken: *token, StatePath: path, Hostname: host}, nil
	case string(CommandApplyUpdate):
		fs := flag.NewFlagSet("apply-update", flag.ContinueOnError)
		fs.SetOutput(io.Discard)
		parentPID := fs.Int("parent-pid", 0, "parent update process PID")
		current := fs.String("current", "", "current agent path")
		staged := fs.String("staged", "", "staged agent path")
		previous := fs.String("previous", "", "rollback agent path")
		health := fs.String("health", "", "health marker path")
		deadlineUnix := fs.String("deadline-unix", "", "health deadline unix seconds")
		if err := fs.Parse(args[1:]); err != nil {
			return Command{}, err
		}
		if fs.NArg() != 0 {
			return Command{}, errors.New("apply-update accepts no positional arguments")
		}
		deadline, err := strconv.ParseInt(strings.TrimSpace(*deadlineUnix), 10, 64)
		if err != nil || deadline <= 0 || *parentPID <= 0 {
			return Command{}, errors.New("apply-update requires valid parent PID and deadline")
		}
		paths := []string{strings.TrimSpace(*current), strings.TrimSpace(*staged), strings.TrimSpace(*previous), strings.TrimSpace(*health)}
		for _, path := range paths {
			if path == "" {
				return Command{}, errors.New("apply-update transaction paths are incomplete")
			}
		}
		return Command{Kind: CommandApplyUpdate, ParentPID: *parentPID, CurrentPath: paths[0], StagedPath: paths[1], PreviousPath: paths[2], HealthPath: paths[3], DeadlineUnix: deadline}, nil
	default:
		return Command{}, errors.New("unknown command; expected version, enroll, run or update")
	}
}
