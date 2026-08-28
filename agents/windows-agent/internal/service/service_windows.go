//go:build windows

package service

import (
	"context"
	"errors"

	"golang.org/x/sys/windows/svc"
)

const ServiceName = "ITGuardianAgent"

func IsWindowsService() (bool, error) {
	return svc.IsWindowsService()
}

func RunWindowsService(run RunFunc) error {
	if run == nil {
		return errors.New("service worker is required")
	}
	return svc.Run(ServiceName, &handler{run: run})
}

type handler struct{ run RunFunc }

func (h *handler) Execute(_ []string, requests <-chan svc.ChangeRequest, status chan<- svc.Status) (bool, uint32) {
	status <- svc.Status{State: svc.StartPending}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	errCh := make(chan error, 1)
	go func() { errCh <- h.run(ctx) }()
	running := svc.Status{State: svc.Running, Accepts: svc.AcceptStop | svc.AcceptShutdown}
	status <- running
	for {
		select {
		case err := <-errCh:
			if err != nil && !errors.Is(err, context.Canceled) {
				return true, 1
			}
			return false, 0
		case request := <-requests:
			switch request.Cmd {
			case svc.Interrogate:
				status <- running
			case svc.Stop, svc.Shutdown:
				status <- svc.Status{State: svc.StopPending}
				cancel()
				err := <-errCh
				if err != nil && !errors.Is(err, context.Canceled) {
					return true, 1
				}
				return false, 0
			default:
				status <- running
			}
		}
	}
}
