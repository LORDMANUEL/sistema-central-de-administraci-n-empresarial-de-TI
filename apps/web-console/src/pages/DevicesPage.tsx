import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { api } from '../api/client'
import type { Device } from '../api/types'
import { DeviceTable } from '../features/devices/DeviceTable'
import { EmptyState, ErrorState, LoadingState } from '../components/PageState'

export function DevicesPage() {
  const [state, setState] = useState('')
  const [search, setSearch] = useState('')
  const devices = useQuery({ queryKey: ['devices', state], queryFn: () => api.get<Device[]>(`/devices${api.query({ state })}`) })
  const filtered = useMemo(() => (devices.data ?? []).filter((device) => `${device.device_id} ${device.guardian_asset_id} ${device.platform} ${device.agent_version}`.toLowerCase().includes(search.toLowerCase())), [devices.data, search])
  return <section className="section section--flush"><div className="toolbar"><div className="search-box"><Search size={17}/><input aria-label="Buscar dispositivos" placeholder="Buscar por ID, activo o plataforma" value={search} onChange={(e)=>setSearch(e.target.value)} /></div><select aria-label="Filtrar estado" value={state} onChange={(e)=>setState(e.target.value)}><option value="">Todos los estados</option><option value="online">Online</option><option value="offline">Offline</option></select></div>{devices.isLoading ? <LoadingState/> : devices.error ? <ErrorState message={(devices.error as Error).message}/> : filtered.length ? <DeviceTable devices={filtered}/> : <EmptyState title="No hay dispositivos" body="No existen endpoints que coincidan con este filtro."/>}</section>
}
