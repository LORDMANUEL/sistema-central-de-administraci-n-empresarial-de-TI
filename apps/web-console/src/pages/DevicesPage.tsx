import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { api } from '../api/client'
import type { Asset, Device } from '../api/types'
import { DeviceTable } from '../features/devices/DeviceTable'
import { EmptyState, ErrorState, LoadingState } from '../components/PageState'
import { useTenantScope } from '../scope/TenantScopeContext'
import { filterDevices } from '../scope/filters'

export function DevicesPage() {
  const { tenantId, siteId } = useTenantScope()
  const [state, setState] = useState('')
  const [search, setSearch] = useState('')
  const devices = useQuery({ queryKey: ['devices', state], queryFn: () => api.get<Device[]>(`/devices${api.query({ state })}`) })
  const assets = useQuery({ queryKey: ['assets', 'scope-support'], queryFn: () => api.get<Asset[]>('/assets') })
  const scoped = useMemo(() => filterDevices(devices.data ?? [], assets.data ?? [], tenantId, siteId), [devices.data, assets.data, tenantId, siteId])
  const filtered = useMemo(() => scoped.filter((device) => `${device.device_id} ${device.guardian_asset_id} ${device.platform} ${device.agent_version}`.toLowerCase().includes(search.toLowerCase())), [scoped, search])
  const loading = devices.isLoading || assets.isLoading
  const error = devices.error ?? assets.error
  return <section className="section section--flush"><div className="toolbar"><div className="search-box"><Search size={17}/><input aria-label="Buscar dispositivos" placeholder="Buscar por ID, activo o plataforma" value={search} onChange={(e)=>setSearch(e.target.value)} /></div><select aria-label="Filtrar estado" value={state} onChange={(e)=>setState(e.target.value)}><option value="">Todos los estados</option><option value="online">Online</option><option value="offline">Offline</option></select></div>{loading ? <LoadingState/> : error ? <ErrorState message={(error as Error).message}/> : filtered.length ? <DeviceTable devices={filtered}/> : <EmptyState title="No hay dispositivos" body="No existen endpoints que coincidan con el alcance o filtro seleccionado."/>}</section>
}
