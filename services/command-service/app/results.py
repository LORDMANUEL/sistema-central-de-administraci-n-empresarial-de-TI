from datetime import datetime, timedelta
from hashlib import sha256
import hmac, json
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from .events import command_event
from .models import Command, CommandResult
from .principal import DevicePrincipal
from .schemas import CommandResultSubmit

class CommandNotFound(RuntimeError): pass
class CommandPrincipalMismatch(RuntimeError): pass
class ExecutionTokenInvalid(RuntimeError): pass
class CommandLeaseExpired(RuntimeError): pass
class CommandStateConflict(RuntimeError): pass
class ResultConflict(RuntimeError): pass
class ResultTimestampInvalid(RuntimeError): pass

def _load_bound_command(session, principal, command_id):
    command = session.execute(select(Command).where(Command.command_id == command_id).with_for_update()).scalar_one_or_none()
    if command is None: raise CommandNotFound("command not found")
    if command.tenant_id != principal.tenant_id or command.guardian_asset_id != principal.guardian_asset_id or command.device_id != principal.device_id: raise CommandPrincipalMismatch("command is not bound to this device principal")
    return command

def _verify_execution_token(command, token):
    if command.execution_token_hash is None: raise ExecutionTokenInvalid("command has no active execution token")
    if not hmac.compare_digest(sha256(token.encode()).hexdigest(), command.execution_token_hash): raise ExecutionTokenInvalid("invalid execution token")

def _verify_lease(command, now):
    if command.lease_expires_at is None or now > command.lease_expires_at: raise CommandLeaseExpired("command execution lease has expired")

def mark_running(session: Session, principal: DevicePrincipal, command_id: UUID, execution_token: str, now: datetime) -> Command:
    command = _load_bound_command(session, principal, command_id); _verify_execution_token(command, execution_token); _verify_lease(command, now)
    if command.state == "dispatched":
        command.state = "running"; session.add(command_event("command.running", command_id=command.command_id, tenant_id=command.tenant_id, asset_id=command.guardian_asset_id, device_id=command.device_id, occurred_at=now))
    elif command.state != "running": raise CommandStateConflict(f"cannot mark command running from state {command.state}")
    session.flush(); return command

def _payload_digest(payload):
    canonical={"result_sequence":payload.result_sequence,"status":payload.status,"exit_code":payload.exit_code,"summary":payload.summary,"started_at":payload.started_at.isoformat(),"finished_at":payload.finished_at.isoformat()}
    return sha256(json.dumps(canonical,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()

def submit_result(session: Session, principal: DevicePrincipal, command_id: UUID, payload: CommandResultSubmit, now: datetime) -> CommandResult:
    command=_load_bound_command(session,principal,command_id); _verify_execution_token(command,payload.execution_token); digest=_payload_digest(payload)
    existing=session.execute(select(CommandResult).where(CommandResult.command_id==command_id,CommandResult.result_sequence==payload.result_sequence)).scalar_one_or_none()
    if existing is not None:
        if existing.payload_digest!=digest: raise ResultConflict("result sequence was already used for a different payload")
        return existing
    if command.state in {"succeeded","failed","cancelled","expired"}: raise CommandStateConflict(f"cannot complete command from terminal state {command.state}")
    _verify_lease(command,now)
    if payload.started_at>now+timedelta(minutes=2) or payload.finished_at>now+timedelta(minutes=2): raise ResultTimestampInvalid("result timestamps cannot be more than two minutes in the future")
    result=CommandResult(command_id=command.command_id,result_sequence=payload.result_sequence,status=payload.status,exit_code=payload.exit_code,summary=payload.summary,started_at=payload.started_at,finished_at=payload.finished_at,payload_digest=digest,received_at=now)
    session.add(result); command.state=payload.status; session.add(command_event(f"command.{payload.status}",command_id=command.command_id,tenant_id=command.tenant_id,asset_id=command.guardian_asset_id,device_id=command.device_id,occurred_at=now,extra={"result_sequence":payload.result_sequence,"exit_code":payload.exit_code})); session.flush(); return result
