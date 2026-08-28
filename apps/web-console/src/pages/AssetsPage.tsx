import { useMemo, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { api } from '../api/client'
import type { Asset } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '../components/PageState'
import { useTenantScope } from '../scope/TenantScopeContext'
import { filterAssets } from '../scope/filters'

export function AssetsPage() {
  const queryClient = useQueryClient()
  const scope = useTenantScope()
  const [show, setShow] = useState(false)
  const [name, setName] = useState('')
  const [hostname, setHostname] = useState('')
  const [type, setType] = useState('computer')
  const assets = useQuery({
    queryKey: ['assets', scope.tenantId],
    queryFn: () => api.get<Asset[]>(`/assets${api.query({ tenant_id: scope.tenantId })}`),
    enabled: Boolean(scope.tenantId),
  })
  const scoped = useMemo(() => filterAssets(assets.data ?? [], scope.tenantId, scope.siteId), [assets.data, scope.tenantId, scope.siteId])
  const selectedTenant = scope.tenants.find((tenant) => tenant.id === scope.tenantId)
  const selectedSite = scope.sites.find((site) => site.id === scope.siteId)
  const create = useMutation({
    mutationFn: () => api.post<Asset>('/assets', { tenant_id: scope.tenantId, asset_type: type, display_name: name, hostname: hostname || null, site_id: scope.siteId || null, department_id: null, serial_number: null }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['assets'] }); setShow(false); setName(''); setHostname('') },
  })
  function submit(event: FormEvent) { event.preventDefault(); if (scope.tenantId) void create.mutateAsync() }
  const loading = scope.loading || (Boolean(scope.tenantId) && assets.isLoading)
  return <section className="section section--flush"><div className="toolbar"><div><strong>Inventario canónico</strong><span className="muted"> {selectedTenant?.name ?? 'Sin empresa'}{selectedSite ? ` · ${selectedSite.name}` : ''}</span></div><button className="button button--primary" disabled={!scope.tenantId} onClick={()=>setShow(!show)}><Plus size={16}/>Nuevo activo</button></div>{show&&<form className="inline-form" onSubmit={submit}><label>Empresa<input value={selectedTenant?.name ?? ''} readOnly /></label><label>Sede<input value={selectedSite?.name ?? 'Sin sede específica'} readOnly /></label><label>Nombre<input required value={name} onChange={e=>setName(e.target.value)}/></label><label>Hostname<input value={hostname} onChange={e=>setHostname(e.target.value)}/></label><label>Tipo<input required value={type} onChange={e=>setType(e.target.value)}/></label><button className="button button--primary" disabled={create.isPending}>Guardar</button>{create.error&&<p className="form-error">{(create.error as Error).message}</p>}</form>}{loading?<LoadingState/>:assets.error?<ErrorState message={(assets.error as Error).message}/>:scoped.length?<div className="table-wrap"><table><thead><tr><th>Activo</th><th>Hostname</th><th>Tipo</th><th>Estado</th><th>Sede</th></tr></thead><tbody>{scoped.map(a=><tr key={a.guardian_asset_id}><td><strong>{a.display_name}</strong><small>{a.guardian_asset_id.slice(0,8)}…</small></td><td>{a.hostname??'—'}</td><td>{a.asset_type}</td><td><StatusBadge value={a.status}/></td><td>{scope.sites.find(site=>site.id===a.site_id)?.name??(a.site_id?a.site_id.slice(0,8)+'…':'—')}</td></tr>)}</tbody></table></div>:<EmptyState title="Sin activos" body="No hay activos en el alcance seleccionado."/>}</section>
}
