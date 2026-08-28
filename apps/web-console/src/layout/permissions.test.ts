import { describe, expect, it } from 'vitest'
import { canNavigate } from './permissions'

describe('web console navigation RBAC', () => {
  it('keeps platform administration exclusive to platform_admin', () => {
    expect(canNavigate('platform_admin', 'users')).toBe(true)
    expect(canNavigate('org_admin', 'users')).toBe(false)
    expect(canNavigate('auditor', 'users')).toBe(false)
    expect(canNavigate('viewer', 'users')).toBe(false)
  })

  it('limits write-oriented endpoint views for auditor and viewer', () => {
    for (const section of ['commands', 'enrollment'] as const) {
      expect(canNavigate('platform_admin', section)).toBe(true)
      expect(canNavigate('it_operator', section)).toBe(true)
      expect(canNavigate('helpdesk', section)).toBe(section === 'commands')
      expect(canNavigate('auditor', section)).toBe(false)
      expect(canNavigate('viewer', section)).toBe(false)
    }
  })

  it('allows auditor to read audit and viewer to read inventory', () => {
    expect(canNavigate('auditor', 'audit')).toBe(true)
    expect(canNavigate('viewer', 'devices')).toBe(true)
    expect(canNavigate('viewer', 'assets')).toBe(true)
    expect(canNavigate('viewer', 'audit')).toBe(false)
  })
})
