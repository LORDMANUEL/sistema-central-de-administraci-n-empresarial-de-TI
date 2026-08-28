import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Asset, Command } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '../components/PageState'
import { useTenantScope } from '../scope/TenantScopeContext'
import { filterCommands } from '../scope/filters'

const terminal = new Set(['succeeded','failed','cancelled','expired'])

export function CommandsPage() {
  const { tenantId, siteId } = useTenantScope()
  const [state, setState] = useState('')
  const queryClient = useQueryClient()
  const commands = useQuery({ queryKey: ['commands', 'global', state], queryFn: () => api.get<Command[]>(`/commands${api.query({ state, limit: 100 })}`), refetchInterval: 15_000 })
  const assets = useQuery({ queryKey: ['assets', 'scope-support'], queryFn: () => api.get<Asset[]>('/assets') })
  const scoped = useMemo(() => filterCommands(commands.data ?? [], assets.data ?? [], tenantId, siteId), [commands.data, assets.data, tenantId, siteId])
  const cancel = useMutation({ mutationFn: (id:string)=>api.post<Command>(`/commands/${id}/cancel`), onSuccess:()=>queryClient.invalidateQueries({queryKey:['commands']}) })
  const loading = commands.isLoading || assets.isLoading
  const error = commands.error ?? assets.error
  return <section className="section section--flush"><div className="toolbar"><div><strong>Operaciones remotas</strong><span className="muted"> La ejecución arbitraria de shell está deshabilitada.</span></div><select aria-label="Filtrar comandos por estado" value={state} onChange={(e)=>setState(e.target.value)}><option value="">Todos</option>{['queued','leased','running','succeeded','failed','cancelled','expired'].map((value)=><option key={value}>{value}</option>)}</select></div>{loading?<LoadingState/>:error?<ErrorState message={(error as Error).message}/>:scoped.length?<div className="table-wrap"><table><thead><tr><th>Comando</th><th>Dispositivo</th><th>Estado</th><th>Creado</th><th></th></tr></thead><tbody>{scoped.map((command)=><tr key={command.command_id}><td><strong>{command.command_type}</strong><small>{command.command_id.slice(0,8)}…</small></td><td>{command.device_id.slice(0,8)}…</td><td><StatusBadge value={command.state}/></td><td>{new Date(command.created_at).toLocaleString()}</td><td>{!terminal.has(command.state)&&<button className="button button--ghost" onClick={()=>cancel.mutate(command.command_id)} disabled={cancel.isPending}>Cancelar</button>}</td></tr>)}</tbody></table></div>:<EmptyState title="Sin comandos" body="No hay comandos en el alcance seleccionado."/>}</section>
}
