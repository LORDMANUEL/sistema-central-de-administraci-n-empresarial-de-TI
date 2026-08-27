from datetime import UTC,datetime
from uuid import UUID
from fastapi import APIRouter,Depends,Request,status
from sqlalchemy import select
from sqlalchemy.orm import Session
from .acquire import acquire_commands
from .auth import IdentityPrincipal,current_principal
from .database import get_db
from .device_auth import current_device_principal
from .errors import GuardianError
from .events import command_event
from .models import Command
from .principal import DevicePrincipal
from .results import CommandLeaseExpired,CommandNotFound,CommandPrincipalMismatch,CommandStateConflict,ExecutionTokenInvalid,ResultConflict,ResultTimestampInvalid,mark_running,submit_result
from .schemas import CommandCreate,CommandRead,CommandResultSubmit,RunningSubmit
from .service import ActorPrincipal,IdempotencyConflict,create_command

router=APIRouter(prefix="/api/v1")

def _map_runtime(exc):
    if isinstance(exc,CommandNotFound):return GuardianError(404,"command.not_found",str(exc))
    if isinstance(exc,CommandPrincipalMismatch):return GuardianError(403,"command.device_mismatch",str(exc))
    if isinstance(exc,ExecutionTokenInvalid):return GuardianError(401,"command.execution_token_invalid",str(exc))
    if isinstance(exc,CommandLeaseExpired):return GuardianError(409,"command.lease_expired",str(exc))
    if isinstance(exc,ResultConflict):return GuardianError(409,"command.result_conflict",str(exc))
    if isinstance(exc,(CommandStateConflict,ResultTimestampInvalid)):return GuardianError(409,"command.state_conflict",str(exc))
    return GuardianError(500,"command.internal_error","Command operation failed")

@router.post("/commands",response_model=CommandRead,status_code=status.HTTP_201_CREATED)
def create(payload:CommandCreate,request:Request,session:Session=Depends(get_db),principal:IdentityPrincipal=Depends(current_principal)):
    tenant_id=request.app.state.core_validator.validate_target(payload.guardian_asset_id,payload.device_id,principal.bearer_token)
    try: command=create_command(session,ActorPrincipal(tenant_id,UUID(principal.user_id)),payload,datetime.now(UTC));session.commit();session.refresh(command);return command
    except IdempotencyConflict as exc:session.rollback();raise GuardianError(409,"command.idempotency_conflict",str(exc)) from exc

@router.get("/commands/{command_id}",response_model=CommandRead)
def get(command_id:UUID,request:Request,session:Session=Depends(get_db),principal:IdentityPrincipal=Depends(current_principal)):
    command=session.get(Command,command_id)
    if command is None:raise GuardianError(404,"command.not_found","Command not found")
    request.app.state.core_validator.validate_target(command.guardian_asset_id,command.device_id,principal.bearer_token);return command

@router.get("/commands",response_model=list[CommandRead])
def list_commands(request:Request,device_id:UUID|None=None,state:str|None=None,limit:int=50,session:Session=Depends(get_db),principal:IdentityPrincipal=Depends(current_principal)):
    limit=max(1,min(limit,100)); stmt=select(Command)
    if device_id:stmt=stmt.where(Command.device_id==device_id)
    if state:stmt=stmt.where(Command.state==state)
    rows=session.execute(stmt.order_by(Command.created_at.desc()).limit(limit)).scalars().all()
    visible=[]
    for command in rows:
        try:request.app.state.core_validator.validate_target(command.guardian_asset_id,command.device_id,principal.bearer_token);visible.append(command)
        except GuardianError as exc:
            if exc.status_code not in {403,404}:raise
    return visible

@router.post("/commands/{command_id}/cancel",response_model=CommandRead)
def cancel(command_id:UUID,request:Request,session:Session=Depends(get_db),principal:IdentityPrincipal=Depends(current_principal)):
    command=session.execute(select(Command).where(Command.command_id==command_id).with_for_update()).scalar_one_or_none()
    if command is None:raise GuardianError(404,"command.not_found","Command not found")
    request.app.state.core_validator.validate_target(command.guardian_asset_id,command.device_id,principal.bearer_token)
    if command.state in {"succeeded","failed","cancelled","expired"}:raise GuardianError(409,"command.state_conflict","Terminal command cannot be cancelled")
    command.state="cancelled";session.add(command_event("command.cancelled",command_id=command.command_id,tenant_id=command.tenant_id,asset_id=command.guardian_asset_id,device_id=command.device_id,occurred_at=datetime.now(UTC),extra={"actor_user_id":principal.user_id}));session.commit();return command

@router.post("/device/commands/acquire")
def acquire(request:Request,limit:int=10,session:Session=Depends(get_db),principal:DevicePrincipal=Depends(current_device_principal)):
    items=acquire_commands(session,principal,datetime.now(UTC),limit=limit);session.commit();return [{"command_id":str(x.command_id),"command_type":x.command_type,"arguments":x.arguments,"execution_token":x.execution_token,"lease_expires_at":x.lease_expires_at.isoformat(),"expires_at":x.expires_at.isoformat()} for x in items]

@router.post("/device/commands/{command_id}/running")
def running(command_id:UUID,payload:RunningSubmit,session:Session=Depends(get_db),principal:DevicePrincipal=Depends(current_device_principal)):
    try:command=mark_running(session,principal,command_id,payload.execution_token,datetime.now(UTC));session.commit();return {"command_id":str(command.command_id),"state":command.state}
    except Exception as exc:session.rollback();raise _map_runtime(exc) from exc

@router.post("/device/commands/{command_id}/result")
def result(command_id:UUID,payload:CommandResultSubmit,session:Session=Depends(get_db),principal:DevicePrincipal=Depends(current_device_principal)):
    try:r=submit_result(session,principal,command_id,payload,datetime.now(UTC));session.commit();return {"result_id":str(r.result_id),"command_id":str(r.command_id),"result_sequence":r.result_sequence,"status":r.status}
    except Exception as exc:session.rollback();raise _map_runtime(exc) from exc
