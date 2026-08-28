package app

import (
	"errors"
	"flag"
	"io"
	"os"
	"strings"

	"github.com/LORDMANUEL/sistema-central-de-administraci-n-empresarial-de-TI/agents/windows-agent/internal/config"
)

type CommandKind string

const (
	CommandVersion CommandKind = "version"
	CommandEnroll  CommandKind = "enroll"
	CommandRun     CommandKind = "run"
)

type Command struct {
	Kind            CommandKind
	ConfigPath      string
	GatewayURL      string
	EnrollmentToken string
	StatePath       string
	Hostname        string
}

func ParseArgs(args []string) (Command, error) {
	if len(args) == 0 {
		return Command{}, errors.New("command is required: version, enroll or run")
	}
	switch args[0] {
	case string(CommandVersion):
		if len(args) != 1 {
			return Command{}, errors.New("version accepts no arguments")
		}
		return Command{Kind: CommandVersion}, nil
	case string(CommandRun):
		fs := flag.NewFlagSet("run", flag.ContinueOnError)
		fs.SetOutput(io.Discard)
		cfg := fs.String("config", "", "runtime config path")
		if err := fs.Parse(args[1:]); err != nil {
			return Command{}, err
		}
		if fs.NArg() != 0 {
			return Command{}, errors.New("run accepts no positional arguments")
		}
		path := strings.TrimSpace(*cfg)
		if path == "" {
			path = config.DefaultDataDir() + string(os.PathSeparator) + "agent.json"
		}
		return Command{Kind: CommandRun, ConfigPath: path}, nil
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
	default:
		return Command{}, errors.New("unknown command; expected version, enroll or run")
	}
}
