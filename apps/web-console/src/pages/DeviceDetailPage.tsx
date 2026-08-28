import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Clock3, Fingerprint, Laptop2 } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Asset, Command, Device, TelemetryLatest } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '../components/PageState'
import { TelemetryPanel } from '../features/devices/TelemetryPanel'
import { CommandForm } from '../features/commands/CommandForm'
import { relativeTime } from '../lib/guardian'
import { useTenantScope } from '../scope/TenantScopeContext'
import { useSession } from '../session/SessionContext'
import { canNavigate } from '../layout/permissions'

export function DeviceDetailPage() {
  const { deviceId = '' } = useParams()
  const scope = useTenantScope()
  const { user } = useSession()
  const device = useQuery({ queryKey: ['device', deviceId], queryFn: () => api.get<Device>(`/devices/${deviceId}`), enabled: !!deviceId })
  const asset = useQuery({ queryKey: ['asset', device.data?.guardian_asset_id], queryFn: () => api.get<Asset>(`/assets/${device.data!.guardian_asset_id}`), enabled: Boolean(device.data?.guardian_asset_id) })
  const inScope = Boolean(device.data && asset.data && device.data.tenant_id === scope.tenantId && (!scope.siteId || asset.data.site_id === scope.siteId))
  const canCommand = Boolean(user && canNavigate(user.role, 'commands'))
  const telemetry = useQuery({ queryKey: ['telemetry', deviceId], queryFn: () => api.get<TelemetryLatest>(`/telemetry/devices/${deviceId}/latest`), enabled: Boolean(deviceId && inScope), refetchInterval: 30_000 })
  const commands = useQuery({ queryKey: ['commands', deviceId], queryFn: () => api.get<Command[]>(`/commands${api.query({ device_id: deviceId, limit: 20 })}`), enabled: Boolean(deviceId && inScope && canCommand), refetchInterval: 15_000 })
  if (device.isLoading || asset.isLoading || scope.loading) return <LoadingState/>
  if (!device.data || device.error) return <ErrorState message={(device.error as Error)?.message || 'No se encontró el dispositivo'}/>
  if (asset.error) return <ErrorState message={(asset.error as Error).message}/>
  if (!inScope) return <EmptyState title="Fuera del alcance" body="Este dispositivo no pertenece a la empresa/sede seleccionada."/>
  const item = device.data
  return <><Link to="/devices" className="back-link"><ArrowLeft size={16}/> Dispositivos</Link><div className="detail-hero"><div><div className="detail-title"><Laptop2 size={23}/><h2>{item.platform === 'windows' ? 'Windows endpoint' : item.platform}</h2><StatusBadge value={item.state}/></div><p>{item.device_id}</p></div><div className="detail-meta"><div><Clock3 size={16}/><span>Última conexión</span><strong>{relativeTime(item.last_seen_at)}</strong></div><div><Fingerprint size={16}/><span>Agent</span><strong>{item.agent_version}</strong></div></div></div><section className="section"><div className="section-heading"><div><h2>Telemetría actual</h2><p>Últimas muestras aceptadas por Telemetry Service.</p></div></div>{telemetry.isLoading ? <LoadingState/> : telemetry.error ? <ErrorState message={(telemetry.error as Error).message}/> : <TelemetryPanel samples={telemetry.data?.samples ?? []}/>}</section>{canCommand?<div className="two-column"><section className="section"><div className="section-heading"><div><h2>Acción remota segura</h2><p>Solo comandos tipados permitidos por el agente.</p></div></div><CommandForm device={item}/></section><section className="section"><div className="section-heading"><div><h2>Comandos recientes</h2><p>Historial para este dispositivo.</p></div></div><div className="compact-list">{(commands.data ?? []).map((command)=><div key={command.command_id}><div><strong>{command.command_type}</strong><span>{new Date(command.created_at).toLocaleString()}</span></div><StatusBadge value={command.state}/></div>)}{commands.data?.length === 0 && <span className="muted">Sin comandos todavía.</span>}</div></section></div>:<section className="section"><p className="muted">Tu rol tiene acceso de lectura al dispositivo; las operaciones remotas no están habilitadas.</p></section>}</>
}
