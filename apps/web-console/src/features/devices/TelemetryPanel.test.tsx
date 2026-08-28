import { render, screen } from '@testing-library/react'
import { TelemetryPanel } from './TelemetryPanel'

it('renders CPU memory and per-volume disk telemetry from backend samples', () => {
  render(<TelemetryPanel samples={[
    { metric: 'cpu.utilization_pct', value: 42.5, labels: {}, observed_at: '2026-08-28T12:00:00Z', batch_id: 'b1' },
    { metric: 'memory.used_bytes', value: 4 * 1024 ** 3, labels: {}, observed_at: '2026-08-28T12:00:00Z', batch_id: 'b1' },
    { metric: 'memory.total_bytes', value: 8 * 1024 ** 3, labels: {}, observed_at: '2026-08-28T12:00:00Z', batch_id: 'b1' },
    { metric: 'disk.free_bytes', value: 50 * 1024 ** 3, labels: { volume: 'C:' }, observed_at: '2026-08-28T12:00:00Z', batch_id: 'b1' },
    { metric: 'disk.total_bytes', value: 100 * 1024 ** 3, labels: { volume: 'C:' }, observed_at: '2026-08-28T12:00:00Z', batch_id: 'b1' },
  ]} />)
  expect(screen.getByText('42.5%')).toBeInTheDocument()
  expect(screen.getByText(/4.0 GB.*8.0 GB/)).toBeInTheDocument()
  expect(screen.getByText('C:')).toBeInTheDocument()
  expect(screen.getByText(/50.0 GB libres/)).toBeInTheDocument()
})
