import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, ShieldAlert } from 'lucide-react'
import { api } from '../api/client'
import type { AuditRecordList, AuditVerification } from '../api/types'
import { StatusBadge } from '../components/StatusBadge'
import { EmptyState, ErrorState, LoadingState } from '../components/PageState'
import { useTenantScope } from '../scope/TenantScopeContext'

export function AuditPage(){
 const scope=useTenantScope();const tenantName=scope.tenants.find(t=>t.id===scope.tenantId)?.name??'Empresa'
 const verify=useQuery({queryKey:['audit','verify',scope.tenantId],queryFn:()=>api.get<AuditVerification>(`/audit/verify${api.query({tenant_id:scope.tenantId})}`),enabled:Boolean(scope.tenantId),retry:false});const records=useQuery({queryKey:['audit','records',scope.tenantId],queryFn:()=>api.get<AuditRecordList>(`/audit/records${api.query({tenant_id:scope.tenantId,limit:100})}`),enabled:Boolean(scope.tenantId)})
 if(scope.loading)return <LoadingState/>;if(scope.error)return <ErrorState message={scope.error.message}/>;if(!scope.tenantId)return <EmptyState title="Sin empresa seleccionada" body="Selecciona una empresa para consultar su audit trail."/>
 return <div className="stack"><section className="audit-banner"><div className={verify.data?.valid?'audit-icon audit-icon--ok':'audit-icon audit-icon--bad'}>{verify.data?.valid?<CheckCircle2/>:<ShieldAlert/>}</div><div><span>Integridad de cadena · {tenantName}</span><strong>{verify.isLoading?'Verificando…':verify.data?.valid?'Cadena íntegra':'Requiere revisión'}</strong><p>{verify.data?`${verify.data.record_count} registros · secuencia ${verify.data.last_sequence}`:'Validación criptográfica del audit trail.'}{scope.siteId?' · Audit se verifica a nivel de empresa; la sede no altera la cadena.':''}</p></div></section><section className="section section--flush">{records.isLoading?<LoadingState/>:records.error?<ErrorState message={(records.error as Error).message}/>:records.data?.items.length?<div className="table-wrap"><table><thead><tr><th>Sec.</th><th>Acción</th><th>Recurso</th><th>Origen</th><th>Resultado</th><th>Fecha</th></tr></thead><tbody>{records.data.items.map(r=><tr key={r.id}><td>{r.sequence}</td><td><strong>{r.action}</strong><small>{r.actor_type}{r.actor_user_id?` · ${r.actor_user_id.slice(0,8)}…`:''}</small></td><td>{r.resource_type}<small>{r.resource_id?.slice(0,8)??'—'}</small></td><td>{r.source_service}</td><td><StatusBadge value={r.outcome}/></td><td>{new Date(r.occurred_at).toLocaleString()}</td></tr>)}</tbody></table></div>:<EmptyState title="Sin registros" body="No hay eventos de auditoría visibles para la empresa seleccionada."/>}</section></div>
}
