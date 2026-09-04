import type { TelemetrySample } from '../../api/types'
import { formatBytes, telemetryValue } from '../../lib/guardian'

export function TelemetryPanel({ samples }: { samples: TelemetrySample[] }) {
  const cpu = telemetryValue(samples, 'cpu.utilization_pct')
  const memoryUsed = telemetryValue(samples, 'memory.used_bytes')
  const memoryTotal = telemetryValue(samples, 'memory.total_bytes')
  const volumes = Array.from(new Set(samples.filter((sample) => sample.metric.startsWith('disk.')).map((sample) => sample.labels.volume).filter(Boolean))).sort()
  const rx = telemetryValue(samples, 'network.rx_bytes_total')
  const tx = telemetryValue(samples, 'network.tx_bytes_total')

  return (
    <section className="telemetry-grid" aria-label="Telemetría actual">
      <div className="metric"><span>CPU</span><strong>{cpu === undefined ? '—' : `${cpu.toFixed(1)}%`}</strong></div>
      <div className="metric"><span>Memoria</span><strong>{memoryUsed === undefined || memoryTotal === undefined ? '—' : `${formatBytes(memoryUsed)} / ${formatBytes(memoryTotal)}`}</strong></div>
      <div className="metric"><span>Red acumulada</span><strong>{rx === undefined && tx === undefined ? '—' : `↓ ${formatBytes(rx ?? 0)} · ↑ ${formatBytes(tx ?? 0)}`}</strong></div>
      {volumes.map((volume) => {
        const free = telemetryValue(samples, 'disk.free_bytes', volume)
        const total = telemetryValue(samples, 'disk.total_bytes', volume)
        return <div className="metric" key={volume}><span>{volume}</span><strong>{free === undefined ? '—' : `${formatBytes(free)} libres`}{total === undefined ? '' : ` / ${formatBytes(total)}`}</strong></div>
      })}
    </section>
  )
}
