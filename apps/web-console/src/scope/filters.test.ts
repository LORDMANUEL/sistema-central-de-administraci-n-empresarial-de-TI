import { describe, expect, it } from 'vitest'
import type { Asset, AuditRecord, Command, Device, Enrollment, EnrollmentToken } from '../api/types'
import { filterAssets, filterAudit, filterCommands, filterDevices, filterEnrollments, filterTokens } from './filters'

const assets = [
  { guardian_asset_id: 'a1', tenant_id: 't1', site_id: 's1' },
  { guardian_asset_id: 'a2', tenant_id: 't1', site_id: 's2' },
  { guardian_asset_id: 'a3', tenant_id: 't2', site_id: 's3' },
] as Asset[]

it('filters assets and device-related records by tenant and site asset membership', () => {
  expect(filterAssets(assets, 't1', 's1').map((item) => item.guardian_asset_id)).toEqual(['a1'])
  const devices = [
    { device_id: 'd1', tenant_id: 't1', guardian_asset_id: 'a1' },
    { device_id: 'd2', tenant_id: 't1', guardian_asset_id: 'a2' },
    { device_id: 'd3', tenant_id: 't2', guardian_asset_id: 'a3' },
  ] as Device[]
  expect(filterDevices(devices, assets, 't1', 's1').map((item) => item.device_id)).toEqual(['d1'])
  const commands = devices.map((device, index) => ({ command_id: `c${index}`, tenant_id: device.tenant_id, guardian_asset_id: device.guardian_asset_id })) as Command[]
  expect(filterCommands(commands, assets, 't1', 's1')).toHaveLength(1)
})

it('filters enrollment and audit records without leaking other tenants', () => {
  const tokens = [{ id: 'x1', tenant_id: 't1', asset_id: 'a1' }, { id: 'x2', tenant_id: 't1', asset_id: 'a2' }] as EnrollmentToken[]
  const enrollments = [{ device_id: 'd1', tenant_id: 't1', asset_id: 'a1' }, { device_id: 'd2', tenant_id: 't1', asset_id: 'a2' }] as Enrollment[]
  expect(filterTokens(tokens, assets, 't1', 's1').map((item) => item.id)).toEqual(['x1'])
  expect(filterEnrollments(enrollments, assets, 't1', 's1').map((item) => item.device_id)).toEqual(['d1'])
  const audit = [{ id: 'r1', tenant_id: 't1' }, { id: 'r2', tenant_id: 't2' }, { id: 'r3', tenant_id: null }] as AuditRecord[]
  expect(filterAudit(audit, 't1').map((item) => item.id)).toEqual(['r1'])
})
