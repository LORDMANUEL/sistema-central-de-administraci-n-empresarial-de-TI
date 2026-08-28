import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Command } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '../components/PageState'

const terminal = new Set(['succeeded','failed','cancelled','expired'])

export function CommandsPage() {
  const [state, setState] = useState('')
  const queryClient = useQueryClient()
  const commands = useQuery({ queryKey: ['commands', 'global', state], queryFn: () => api.get<Command[]>(`/commands${api.query({ state, limit: 100 })}`), refetchInterval: 15_000 })
  const cancel = useMutation({ mutationFn: (id:string)=>api.post<Command>(`/commands/${id}/cancel`), onSuccess:()=>queryClient.invalidateQueries({queryKey:['commands']}) })
  return <section className="section section--flush"><div className="toolbar"><div><strong>Operaciones remotas</strong><span className="muted"> La ejecución arbitraria de shell está deshabilitada.</span></div><select value={state} onChange={(e)=>setState(e.target.value)}><option value="">Todos</option>{['queued','leased','running','succeeded','failed','cancelled','expired'].map((value)=><option key={value}>{value}</option>)}</select></div>{commands.isLoading?<LoadingState/>:commands.error?<ErrorState message={(commands.error as Error).message}/>:commands.data?.length?<div className="table-wrap"><table><thead><tr><th>Comando</th><th>Dispositivo</th><th>Estado</th><th>Creado</th><th></th></tr></thead><tbody>{commands.data.map((command)=><tr key={command.command_id}><td><strong>{command.command_type}</strong><small>{command.command_id.slice(0,8)}…</small></td><td>{command.device_id.slice(0,8)}…</td><td><StatusBadge value={command.state}/></td><td>{new Date(command.created_at).toLocaleString()}</td><td>{!terminal.has(command.state)&&<button className="button button--ghost" onClick={()=>cancel.mutate(command.command_id)} disabled={cancel.isPending}>Cancelar</button>}</td></tr>)}</tbody></table></div>:<EmptyState title="Sin comandos" body="Los comandos creados desde cada dispositivo aparecerán aquí."/>}</section>
}
