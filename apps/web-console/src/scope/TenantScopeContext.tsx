import { createContext, useContext, useEffect, useMemo, useState, type PropsWithChildren } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Site, Tenant } from '../api/types'
import { useSession } from '../session/SessionContext'

interface TenantScopeValue {
  tenantId: string
  siteId: string
  tenants: Tenant[]
  sites: Site[]
  loading: boolean
  error: Error | null
  setTenantId: (tenantId: string) => void
  setSiteId: (siteId: string) => void
}

const TenantScopeContext = createContext<TenantScopeValue | null>(null)

export function TenantScopeProvider({ children }: PropsWithChildren) {
  const { user } = useSession()
  const [tenantId, setTenantState] = useState('')
  const [siteId, setSiteId] = useState('')

  const tenantsQuery = useQuery({
    queryKey: ['scope', 'tenants', user?.id],
    queryFn: () => api.get<Tenant[]>('/tenants'),
    enabled: Boolean(user),
  })
  const tenants = tenantsQuery.data ?? []

  useEffect(() => {
    if (!user) {
      setTenantState('')
      setSiteId('')
      return
    }
    if (!tenants.length) return
    if (!tenantId || !tenants.some((tenant) => tenant.id === tenantId)) {
      setTenantState(tenants[0].id)
      setSiteId('')
    }
  }, [tenantId, tenants, user])

  const sitesQuery = useQuery({
    queryKey: ['scope', 'sites', tenantId],
    queryFn: () => api.get<Site[]>(`/tenants/${tenantId}/sites`),
    enabled: Boolean(user && tenantId),
  })
  const sites = sitesQuery.data ?? []

  useEffect(() => {
    if (siteId && !sites.some((site) => site.id === siteId)) setSiteId('')
  }, [siteId, sites])

  function setTenantId(nextTenantId: string) {
    if (nextTenantId === tenantId) return
    setTenantState(nextTenantId)
    setSiteId('')
  }

  const value = useMemo<TenantScopeValue>(() => ({
    tenantId,
    siteId,
    tenants,
    sites,
    loading: tenantsQuery.isLoading || (Boolean(tenantId) && sitesQuery.isLoading),
    error: (tenantsQuery.error ?? sitesQuery.error ?? null) as Error | null,
    setTenantId,
    setSiteId,
  }), [tenantId, siteId, tenants, sites, tenantsQuery.isLoading, tenantsQuery.error, sitesQuery.isLoading, sitesQuery.error])

  return <TenantScopeContext.Provider value={value}>{children}</TenantScopeContext.Provider>
}

export function useTenantScope() {
  const value = useContext(TenantScopeContext)
  if (!value) throw new Error('useTenantScope must be used within TenantScopeProvider')
  return value
}
