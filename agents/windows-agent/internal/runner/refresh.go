package runner

import "context"

// RefreshTelemetry is the implementation behind the typed inventory.refresh command.
// It intentionally reuses the normal telemetry path, including offline spooling.
func (r *Runner) RefreshTelemetry(ctx context.Context) error {
	if err := r.validate(); err != nil {
		return err
	}
	return r.telemetry(ctx)
}
