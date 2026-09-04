import type { Device, TelemetrySample } from '../api/types'

export type CommandType = 'inventory.refresh' | 'device.reboot' | 'service.restart'

export function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value < 0) return '—'
  if (value === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  if (index === 0) return `${Math.round(value)} B`
  return `${(value / 1024 ** index).toFixed(1)} ${units[index]}`
}

export function summarizeDevices(devices: Device[]) {
  return {
    total: devices.length,
    online: devices.filter((device) => device.state === 'online').length,
    offline: devices.filter((device) => device.state === 'offline').length,
  }
}

export function buildCommandPayload(input: {
  device: Device
  type: CommandType
  delaySeconds?: number
  serviceName?: string
}) {
  let arguments_: Record<string, unknown>
  if (input.type === 'inventory.refresh') {
    arguments_ = {}
  } else if (input.type === 'device.reboot') {
    const delay = input.delaySeconds ?? 0
    if (!Number.isInteger(delay) || delay < 0 || delay > 3600) throw new Error('El retraso debe ser un entero entre 0 y 3600 segundos')
    arguments_ = { delay_seconds: delay }
  } else {
    const serviceName = input.serviceName ?? ''
    if (!/^[A-Za-z0-9_. -]{1,128}$/.test(serviceName)) throw new Error('El nombre del servicio contiene caracteres no permitidos')
    arguments_ = { service_name: serviceName }
  }
  return {
    tenant_id: input.device.tenant_id,
    device_id: input.device.device_id,
    guardian_asset_id: input.device.guardian_asset_id,
    command_type: input.type,
    arguments: arguments_,
    idempotency_key: crypto.randomUUID(),
    expires_in_seconds: 900,
  }
}

export function telemetryValue(samples: TelemetrySample[], metric: string, volume?: string) {
  return samples.find((sample) => sample.metric === metric && (volume === undefined || sample.labels.volume === volume))?.value
}

export function relativeTime(value: string) {
  const timestamp = new Date(value).getTime()
  if (!Number.isFinite(timestamp)) return '—'
  const seconds = Math.round((timestamp - Date.now()) / 1000)
  const formatter = new Intl.RelativeTimeFormat('es', { numeric: 'auto' })
  const ranges: [number, Intl.RelativeTimeFormatUnit][] = [[86400, 'day'], [3600, 'hour'], [60, 'minute']]
  for (const [size, unit] of ranges) {
    if (Math.abs(seconds) >= size) return formatter.format(Math.round(seconds / size), unit)
  }
  return formatter.format(seconds, 'second')
}
