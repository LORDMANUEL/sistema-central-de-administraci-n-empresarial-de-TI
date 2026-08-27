from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .command_types import normalize_command
from .events import command_event, command_wakeup
from .models import Command
from .schemas import CommandCreate


class IdempotencyConflict(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ActorPrincipal:
    tenant_id: UUID
    actor_id: UUID


def _semantic_digest(request: CommandCreate, normalized_arguments: dict) -> str:
    canonical = {"device_id": str(request.device_id), "guardian_asset_id": str(request.guardian_asset_id), "command_type": request.command_type, "arguments": normalized_arguments, "expires_in_seconds": request.expires_in_seconds}
    return sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def create_command(session: Session, actor: ActorPrincipal, request: CommandCreate, now: datetime) -> Command:
    normalized_arguments = normalize_command(request.command_type, request.arguments)
    digest = _semantic_digest(request, normalized_arguments)
    existing = session.execute(select(Command).where(Command.tenant_id == actor.tenant_id, Command.idempotency_key == request.idempotency_key)).scalar_one_or_none()
    if existing is not None:
        if existing.request_digest != digest:
            raise IdempotencyConflict("idempotency key was already used for a different command request")
        return existing
    command = Command(tenant_id=actor.tenant_id, guardian_asset_id=request.guardian_asset_id, device_id=request.device_id, created_by=actor.actor_id, command_type=request.command_type, arguments=normalized_arguments, idempotency_key=request.idempotency_key, request_digest=digest, state="queued", created_at=now, expires_at=now + timedelta(seconds=request.expires_in_seconds), dispatch_attempts=0)
    session.add(command)
    session.flush()
    session.add(command_event("command.created", command_id=command.command_id, tenant_id=command.tenant_id, asset_id=command.guardian_asset_id, device_id=command.device_id, occurred_at=now, extra={"command_type": command.command_type, "actor_user_id": str(actor.actor_id)}))
    session.add(command_wakeup(command_id=command.command_id, device_id=command.device_id, tenant_id=command.tenant_id, occurred_at=now))
    session.flush()
    return command
