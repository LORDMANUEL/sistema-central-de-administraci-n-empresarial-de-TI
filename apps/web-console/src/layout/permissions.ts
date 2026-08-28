import type { Role } from '../api/types'

export type ConsoleSection = 'overview' | 'devices' | 'assets' | 'commands' | 'enrollment' | 'organization' | 'audit' | 'users'

const grants: Record<Role, ReadonlySet<ConsoleSection>> = {
  platform_admin: new Set(['overview', 'devices', 'assets', 'commands', 'enrollment', 'organization', 'audit', 'users']),
  org_admin: new Set(['overview', 'devices', 'assets', 'commands', 'enrollment', 'organization', 'audit']),
  security_admin: new Set(['overview', 'devices', 'assets', 'commands', 'audit']),
  it_operator: new Set(['overview', 'devices', 'assets', 'commands', 'enrollment', 'audit']),
  helpdesk: new Set(['overview', 'devices', 'assets', 'commands']),
  auditor: new Set(['overview', 'devices', 'assets', 'audit']),
  viewer: new Set(['overview', 'devices', 'assets']),
}

export function canNavigate(role: Role, section: ConsoleSection): boolean {
  return grants[role].has(section)
}
