import { buildCommandPayload, formatBytes, summarizeDevices } from './guardian'

const device = {
  device_id: '11111111-1111-1111-1111-111111111111',
  tenant_id: '22222222-2222-2222-2222-222222222222',
  guardian_asset_id: '33333333-3333-3333-3333-333333333333',
  session_id: '44444444-4444-4444-4444-444444444444',
  state: 'online',
  agent_version: '0.7.0',
  platform: 'windows',
  platform_version: '11',
  capabilities: ['heartbeat.v1'],
  capability_version: 1,
  last_seen_at: '2026-08-28T12:00:00Z',
}

describe('guardian domain helpers', () => {
  it('formats binary byte quantities', () => {
    expect(formatBytes(0)).toBe('0 B')
    expect(formatBytes(1024)).toBe('1.0 KB')
    expect(formatBytes(1024 * 1024)).toBe('1.0 MB')
  })

  it('summarizes online and offline devices', () => {
    expect(summarizeDevices([device, { ...device, device_id: 'd2', state: 'offline' }])).toEqual({
      total: 2,
      online: 1,
      offline: 1,
    })
  })

  it('builds only the typed command payloads supported by the agent', () => {
    const refresh = buildCommandPayload({ device, type: 'inventory.refresh' })
    expect(refresh.arguments).toEqual({})
    expect(refresh.expires_in_seconds).toBe(900)

    const reboot = buildCommandPayload({ device, type: 'device.reboot', delaySeconds: 30 })
    expect(reboot.arguments).toEqual({ delay_seconds: 30 })

    const restart = buildCommandPayload({ device, type: 'service.restart', serviceName: 'Spooler' })
    expect(restart.arguments).toEqual({ service_name: 'Spooler' })
  })

  it('rejects unsafe reboot and service arguments', () => {
    expect(() => buildCommandPayload({ device, type: 'device.reboot', delaySeconds: 3601 })).toThrow()
    expect(() => buildCommandPayload({ device, type: 'service.restart', serviceName: 'bad/service' })).toThrow()
  })
})
