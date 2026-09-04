import type { Asset, AuditRecord, Command, Device, Enrollment, EnrollmentToken } from '../api/types'

function allowedAssetIds(assets: Asset[], tenantId: string, siteId: string): Set<string> {
  return new Set(filterAssets(assets, tenantId, siteId).map((asset) => asset.guardian_asset_id))
}

export function filterAssets(items: Asset[], tenantId: string, siteId: string): Asset[] {
  if (!tenantId) return []
  return items.filter((item) => item.tenant_id === tenantId && (!siteId || item.site_id === siteId))
}

export function filterDevices(items: Device[], assets: Asset[], tenantId: string, siteId: string): Device[] {
  if (!tenantId) return []
  const allowed = siteId ? allowedAssetIds(assets, tenantId, siteId) : null
  return items.filter((item) => item.tenant_id === tenantId && (!allowed || allowed.has(item.guardian_asset_id)))
}

export function filterCommands(items: Command[], assets: Asset[], tenantId: string, siteId: string): Command[] {
  if (!tenantId) return []
  const allowed = siteId ? allowedAssetIds(assets, tenantId, siteId) : null
  return items.filter((item) => item.tenant_id === tenantId && (!allowed || allowed.has(item.guardian_asset_id)))
}

export function filterTokens(items: EnrollmentToken[], assets: Asset[], tenantId: string, siteId: string): EnrollmentToken[] {
  if (!tenantId) return []
  const allowed = siteId ? allowedAssetIds(assets, tenantId, siteId) : null
  return items.filter((item) => item.tenant_id === tenantId && (!allowed || allowed.has(item.asset_id)))
}

export function filterEnrollments(items: Enrollment[], assets: Asset[], tenantId: string, siteId: string): Enrollment[] {
  if (!tenantId) return []
  const allowed = siteId ? allowedAssetIds(assets, tenantId, siteId) : null
  return items.filter((item) => item.tenant_id === tenantId && (!allowed || allowed.has(item.asset_id)))
}

export function filterAudit(items: AuditRecord[], tenantId: string): AuditRecord[] {
  if (!tenantId) return []
  return items.filter((item) => item.tenant_id === tenantId)
}
