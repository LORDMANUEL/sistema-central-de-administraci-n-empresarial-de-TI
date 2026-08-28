import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, CircleCheck, Cpu, PackageSearch, SquareTerminal } from 'lucide-react'
import { api } from '../api/client'
import type { Asset, AuditVerification, Command, Device } from '../api/types'
import { summarizeDevices } from '../lib/guardian'
import { DeviceTable } from '../features/devices/DeviceTable'
import { ErrorState, LoadingState } from '../components/PageState'
import { useTenantScope } from '../scope/TenantScopeContext'
import { filterAssets, filterCommands, filterDevices } from '../scope/filters'

export function OverviewPage() {
  const scope = useTenantScope()
  const devices = useQuery({ queryKey: ['devices'], queryFn: () => api.get<Device[]>('/devices') })
  const assets = useQuery({ queryKey: ['assets'], queryFn: () => api.get<Asset[]>('/assets') })
  const commands = useQuery({ queryKey: ['commands', 'overview'], queryFn: () => api.get<Command[]>('/commands?limit=100') })
  const audit = useQuery({ queryKey: ['audit', 'verify', scope.tenantId], queryFn: () => api.get<AuditVerification>(`/audit/verify${api.query({ tenant_id: scope.tenantId })}`), enabled: Boolean(scope.tenantId), retry: false })
  const scopedAssets = useMemo(() => filterAssets(assets.data ?? [], scope.tenantId, scope.siteId), [assets.data, scope.tenantId, scope.siteId])
  const scopedDevices = useMemo(() => filterDevices(devices.data ?? [], assets.data ?? [], scope.tenantId, scope.siteId), [devices.data, assets.data, scope.tenantId, scope.siteId])
  const scopedCommands = useMemo(() => filterCommands(commands.data ?? [], assets.data ?? [], scope.tenantId, scope.siteId), [commands.data, assets.data, scope.tenantId, scope.siteId])
  if (devices.isLoading || assets.isLoading || commands.isLoading || scope.loading) return <LoadingState />
  const error = devices.error ?? assets.error ?? commands.error
  if (error) return <ErrorState message={(error as Error).message} />
  const summary = summarizeDevices(scopedDevices)
  return <><div className="kpi-strip"><div><Cpu size={18}/><span>Dispositivos</span><strong>{summary.total}</strong><small>{summary.online} online · {summary.offline} offline</small></div><div><PackageSearch size={18}/><span>Activos</span><strong>{scopedAssets.length}</strong><small>inventario del alcance seleccionado</small></div><div><SquareTerminal size={18}/><span>Comandos recientes</span><strong>{scopedCommands.length}</strong><small>hasta 100 accesibles en el alcance</small></div><div><CircleCheck size={18}/><span>Cadena Audit</span><strong>{audit.data ? (audit.data.valid ? 'Íntegra' : 'Alerta') : '—'}</strong><small>{audit.data ? `${audit.data.record_count} registros` : 'según permisos'}</small></div></div><section className="section"><div className="section-heading"><div><span className="section-icon"><Activity size={17}/></span><div><h2>Estado de endpoints</h2><p>Sesiones reportadas por Agent Control dentro del alcance actual.</p></div></div><a href="/console/devices" className="text-action">Ver todos</a></div>{scopedDevices.length?<DeviceTable devices={scopedDevices.slice(0, 8)} />:<p className="muted">No hay endpoints en el alcance seleccionado.</p>}</section></>
}
