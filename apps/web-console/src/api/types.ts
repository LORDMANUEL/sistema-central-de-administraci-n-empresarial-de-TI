export type Role = 'platform_admin' | 'org_admin' | 'security_admin' | 'it_operator' | 'helpdesk' | 'auditor' | 'viewer'

export interface User {
  id: string
  email: string
  display_name: string
  role: Role
  is_active: boolean
  created_at?: string
  updated_at?: string
}

export interface Tenant {
  id: string
  name: string
  slug: string
  status: string
  timezone: string
  locale: string
  created_at: string
  updated_at: string
}

export interface Site {
  id: string
  tenant_id: string
  code: string
  name: string
  status: string
  timezone: string | null
  country_code: string | null
  region: string | null
  city: string | null
  address_line1: string | null
}

export interface Department {
  id: string
  tenant_id: string
  code: string
  name: string
  status: string
  parent_id: string | null
}

export interface Membership {
  id: string
  tenant_id: string
  user_id: string
  role: string
  is_active: boolean
}

export interface Asset {
  guardian_asset_id: string
  tenant_id: string
  site_id: string | null
  department_id: string | null
  asset_type: string
  display_name: string
  hostname: string | null
  serial_number: string | null
  status: string
  created_at: string
  updated_at: string
}

export interface Device {
  device_id: string
  tenant_id: string
  guardian_asset_id: string
  session_id: string
  state: string
  agent_version: string
  platform: string
  platform_version: string
  capabilities: string[]
  capability_version: number
  last_seen_at: string
}

export interface TelemetrySample {
  metric: string
  value: number
  labels: Record<string, string>
  observed_at: string
  batch_id: string
}

export interface TelemetryLatest {
  device_id: string
  tenant_id: string
  guardian_asset_id: string
  samples: TelemetrySample[]
}

export interface Command {
  command_id: string
  tenant_id: string
  guardian_asset_id: string
  device_id: string
  command_type: string
  arguments: Record<string, unknown>
  state: string
  created_at: string
  expires_at: string
  dispatch_attempts: number
  lease_expires_at: string | null
}

export interface EnrollmentToken {
  id: string
  tenant_id: string
  asset_id: string
  token_hint: string
  token?: string
  status: string
  created_at: string
  expires_at: string
  revoked_at: string | null
  reserved_at: string | null
  consumed_at: string | null
  consumed_device_id: string | null
}

export interface Enrollment {
  device_id: string
  tenant_id: string
  asset_id: string
  platform: string
  hostname: string
  agent_version: string | null
  status: string
  certificate_id: string | null
  certificate_serial_hex: string | null
  certificate_fingerprint_sha256: string | null
  certificate_not_before: string | null
  certificate_not_after: string | null
  failure_code: string | null
  created_at: string
  updated_at: string
  enrolled_at: string | null
}

export interface AuditRecord {
  id: string
  tenant_id: string | null
  sequence: number
  chain_key: string
  source_event_id: string
  source_type: string
  source_service: string
  actor_user_id: string | null
  actor_type: string
  action: string
  resource_type: string
  resource_id: string | null
  outcome: string
  request_id: string | null
  occurred_at: string
  ingested_at: string
  metadata: Record<string, unknown>
  prev_hash: string
  record_hash: string
}

export interface AuditRecordList {
  items: AuditRecord[]
  next_after_sequence: number | null
}

export interface AuditVerification {
  chain_key: string
  valid: boolean
  record_count: number
  last_sequence: number
  last_hash: string
  first_invalid_sequence: number | null
  first_invalid_record_id: string | null
}
