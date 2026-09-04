import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { DeviceTable } from './DeviceTable'

const devices = [
  {
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
  },
]

it('renders device state and agent information in a table', () => {
  render(<MemoryRouter><DeviceTable devices={devices} /></MemoryRouter>)
  expect(screen.getByRole('table')).toBeInTheDocument()
  expect(screen.getByText('ONLINE')).toBeInTheDocument()
  expect(screen.getByText('0.7.0')).toBeInTheDocument()
  expect(screen.getByText('Windows 11')).toBeInTheDocument()
})
