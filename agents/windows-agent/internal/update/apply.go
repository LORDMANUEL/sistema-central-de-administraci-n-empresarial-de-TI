package update

import (
	"context"
	"errors"
	"fmt"
	"os"
	"time"
)

type ServiceController interface {
	Stop(context.Context) error
	Start() error
}

type ParentWaiter func(context.Context, int) error

func FinalizeUpdate(ctx context.Context, promotion Promotion, service ServiceController, parentPID int, waitParent ParentWaiter, pollInterval time.Duration) (Action, error) {
	if service == nil || waitParent == nil || parentPID <= 0 {
		return "", errors.New("update helper dependencies are incomplete")
	}
	if pollInterval <= 0 || pollInterval > time.Second {
		return "", errors.New("update helper poll interval is outside policy")
	}
	if err := promotion.validate(); err != nil {
		return "", err
	}
	if err := waitParent(ctx, parentPID); err != nil {
		return "", err
	}
	if err := service.Stop(ctx); err != nil {
		return "", fmt.Errorf("stop agent service: %w", err)
	}
	if err := promotion.Activate(); err != nil {
		return "", fmt.Errorf("activate staged agent: %w", err)
	}
	if err := service.Start(); err != nil {
		rollbackAction, rollbackErr := forceRollback(promotion, service)
		if rollbackErr != nil {
			return "", fmt.Errorf("start updated service: %v; rollback failed: %w", err, rollbackErr)
		}
		return rollbackAction, fmt.Errorf("start updated service: %w", err)
	}

	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()
	for {
		if _, err := os.Stat(promotion.HealthMarker); err == nil {
			action, evalErr := promotion.Evaluate(time.Now().UTC())
			if evalErr != nil {
				return "", evalErr
			}
			if action != ActionCommitted {
				return "", fmt.Errorf("health marker did not commit update: %s", action)
			}
			return action, nil
		} else if !os.IsNotExist(err) {
			return "", err
		}
		if !time.Now().UTC().Before(promotion.Deadline) {
			return forceRollback(promotion, service)
		}
		select {
		case <-ctx.Done():
			return "", ctx.Err()
		case <-ticker.C:
		}
	}
}

func forceRollback(promotion Promotion, service ServiceController) (Action, error) {
	rollbackCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	if err := service.Stop(rollbackCtx); err != nil {
		return "", fmt.Errorf("stop unhealthy updated service: %w", err)
	}
	action, err := promotion.Evaluate(promotion.Deadline.Add(time.Nanosecond))
	if err != nil {
		return "", err
	}
	if action != ActionRolledBack {
		return "", fmt.Errorf("expected rollback action, got %s", action)
	}
	if err := service.Start(); err != nil {
		return "", fmt.Errorf("restart rolled-back service: %w", err)
	}
	return action, nil
}
