import { useQuery } from '@tanstack/react-query'
import { Activity, CircleCheck, Cpu, PackageSearch, SquareTerminal } from 'lucide-react'
import { api } from '../api/client'
import type { Asset, AuditVerification, Command, Device } from '../api/types'
import { summarizeDevices } from '../lib/guardian'
import { DeviceTable } from '../features/devices/DeviceTable'
import { ErrorState, LoadingState } from '../components/PageState'

export function OverviewPage() {
  const devices = useQuery({ queryKey: ['devices'], queryFn: () => api.get<Device[]>('/devices') })
  const assets = useQuery({ queryKey: ['assets'], queryFn: () => api.get<Asset[]>('/assets') })
  const commands = useQuery({ queryKey: ['commands'], queryFn: () => api.get<Command[]>('/commands?limit=10') })
  const audit = useQuery({ queryKey: ['audit', 'verify', 'platform'], queryFn: () => api.get<AuditVerification>('/audit/verify'), retry: false })
  if (devices.isLoading || assets.isLoading || commands.isLoading) return <LoadingState />
  if (devices.error) return <ErrorState message={(devices.error as Error).message} />
  const summary = summarizeDevices(devices.data ?? [])
  return <><div className="kpi-strip"><div><Cpu size={18}/><span>Dispositivos</span><strong>{summary.total}</strong><small>{summary.online} online · {summary.offline} offline</small></div><div><PackageSearch size={18}/><span>Activos</span><strong>{assets.data?.length ?? '—'}</strong><small>inventario canónico visible</small></div><div><SquareTerminal size={18}/><span>Comandos recientes</span><strong>{commands.data?.length ?? '—'}</strong><small>últimos 10 accesibles</small></div><div><CircleCheck size={18}/><span>Cadena Audit</span><strong>{audit.data ? (audit.data.valid ? 'Íntegra' : 'Alerta') : '—'}</strong><small>{audit.data ? `${audit.data.record_count} registros` : 'según permisos'}</small></div></div><section className="section"><div className="section-heading"><div><span className="section-icon"><Activity size={17}/></span><div><h2>Estado de endpoints</h2><p>Sesiones reportadas por Agent Control.</p></div></div><a href="/console/devices" className="text-action">Ver todos</a></div><DeviceTable devices={(devices.data ?? []).slice(0, 8)} /></section></>
}
