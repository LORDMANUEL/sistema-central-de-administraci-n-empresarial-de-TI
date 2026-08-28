import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { api } from '../api/client'
import type { Asset, Tenant } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '../components/PageState'

export function AssetsPage() {
  const queryClient=useQueryClient(); const [show,setShow]=useState(false); const [tenant,setTenant]=useState(''); const [name,setName]=useState(''); const [hostname,setHostname]=useState(''); const [type,setType]=useState('computer')
  const assets=useQuery({queryKey:['assets'],queryFn:()=>api.get<Asset[]>('/assets')}); const tenants=useQuery({queryKey:['tenants'],queryFn:()=>api.get<Tenant[]>('/tenants')})
  const create=useMutation({mutationFn:()=>api.post<Asset>('/assets',{tenant_id:tenant,asset_type:type,display_name:name,hostname:hostname||null,site_id:null,department_id:null,serial_number:null}),onSuccess:()=>{queryClient.invalidateQueries({queryKey:['assets']});setShow(false);setName('');setHostname('')}})
  function submit(e:FormEvent){e.preventDefault();void create.mutateAsync()}
  return <section className="section section--flush"><div className="toolbar"><div><strong>Inventario canónico</strong><span className="muted"> Assets Service</span></div><button className="button button--primary" onClick={()=>setShow(!show)}><Plus size={16}/>Nuevo activo</button></div>{show&&<form className="inline-form" onSubmit={submit}><label>Empresa<select required value={tenant} onChange={e=>setTenant(e.target.value)}><option value="">Seleccione…</option>{tenants.data?.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label><label>Nombre<input required value={name} onChange={e=>setName(e.target.value)}/></label><label>Hostname<input value={hostname} onChange={e=>setHostname(e.target.value)}/></label><label>Tipo<input required value={type} onChange={e=>setType(e.target.value)}/></label><button className="button button--primary" disabled={create.isPending}>Guardar</button>{create.error&&<p className="form-error">{(create.error as Error).message}</p>}</form>}{assets.isLoading?<LoadingState/>:assets.error?<ErrorState message={(assets.error as Error).message}/>:assets.data?.length?<div className="table-wrap"><table><thead><tr><th>Activo</th><th>Hostname</th><th>Tipo</th><th>Estado</th><th>Empresa</th></tr></thead><tbody>{assets.data.map(a=><tr key={a.guardian_asset_id}><td><strong>{a.display_name}</strong><small>{a.guardian_asset_id.slice(0,8)}…</small></td><td>{a.hostname??'—'}</td><td>{a.asset_type}</td><td><StatusBadge value={a.status}/></td><td>{tenants.data?.find(t=>t.id===a.tenant_id)?.name??a.tenant_id.slice(0,8)+'…'}</td></tr>)}</tbody></table></div>:<EmptyState title="Sin activos" body="Crea el primer activo administrable para comenzar."/>}</section>
}
