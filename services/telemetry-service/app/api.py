from datetime import UTC,datetime,timedelta
from uuid import UUID
from fastapi import APIRouter,Depends,Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from .auth import IdentityPrincipal,current_principal
from .database import get_db
from .device_auth import current_device_principal
from .errors import GuardianError
from .ingest import TelemetryBatchConflict,ingest_batch
from .models import TelemetryBatchRecord,TelemetrySample
from .principal import DevicePrincipal
from .schemas import TelemetryBatchInput
router=APIRouter(prefix="/api/v1")
@router.post("/device/telemetry")
def ingest(payload:TelemetryBatchInput,session:Session=Depends(get_db),principal:DevicePrincipal=Depends(current_device_principal)):
 now=datetime.now(UTC)
 if payload.sent_at<now-timedelta(hours=24) or payload.sent_at>now+timedelta(minutes=2):raise GuardianError(422,"telemetry.sent_at_invalid","Batch timestamp outside accepted window")
 for s in payload.samples:
  if s.observed_at<now-timedelta(hours=24) or s.observed_at>now+timedelta(minutes=2):raise GuardianError(422,"telemetry.observed_at_invalid","Sample timestamp outside accepted window")
 try:ack=ingest_batch(session,principal,payload,now);session.commit();return {"batch_record_id":str(ack.batch_record_id),"accepted_samples":ack.accepted_samples,"duplicate":ack.duplicate}
 except TelemetryBatchConflict as exc:session.rollback();raise GuardianError(409,"telemetry.batch_conflict",str(exc)) from exc
@router.get("/telemetry/devices/{device_id}/latest")
def latest(device_id:UUID,request:Request,session:Session=Depends(get_db),principal:IdentityPrincipal=Depends(current_principal)):
 tenant_id,asset_id=request.app.state.core_validator.target_for_device(device_id,principal.bearer_token)
 rows=session.execute(select(TelemetrySample,TelemetryBatchRecord).join(TelemetryBatchRecord,TelemetrySample.batch_record_id==TelemetryBatchRecord.batch_record_id).where(TelemetryBatchRecord.device_id==device_id,TelemetryBatchRecord.tenant_id==tenant_id).order_by(TelemetrySample.observed_at.desc())).all();seen=set();latest=[]
 for sample,batch in rows:
  key=(sample.metric,tuple(sorted(sample.labels.items())))
  if key in seen:continue
  seen.add(key);latest.append({"metric":sample.metric,"value":sample.value,"labels":sample.labels,"observed_at":sample.observed_at.isoformat(),"batch_id":str(batch.batch_id)})
 return {"device_id":str(device_id),"tenant_id":str(tenant_id),"guardian_asset_id":str(asset_id),"samples":latest}
