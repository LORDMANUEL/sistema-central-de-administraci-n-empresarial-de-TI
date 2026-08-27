from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .events import command_event
from .models import Command
from .principal import DevicePrincipal

MAX_ACQUIRE_LIMIT = 10
LEASE_SECONDS = 120

@dataclass(frozen=True, slots=True)
class AcquiredCommand:
    command_id: UUID
    command_type: str
    arguments: dict
    execution_token: str
    lease_expires_at: datetime
    expires_at: datetime

def _hash_token(token: str) -> str:
    return sha256(token.encode()).hexdigest()

def acquire_commands(session: Session, principal: DevicePrincipal, now: datetime, *, limit: int = MAX_ACQUIRE_LIMIT) -> list[AcquiredCommand]:
    effective_limit = max(0, min(limit, MAX_ACQUIRE_LIMIT))
    if effective_limit == 0: return []
    expired = session.execute(select(Command).where(Command.tenant_id == principal.tenant_id, Command.guardian_asset_id == principal.guardian_asset_id, Command.device_id == principal.device_id, Command.state == "queued", Command.expires_at <= now).with_for_update()).scalars().all()
    for command in expired:
        command.state = "expired"
        session.add(command_event("command.expired", command_id=command.command_id, tenant_id=command.tenant_id, asset_id=command.guardian_asset_id, device_id=command.device_id, occurred_at=now))
    candidates = session.execute(select(Command).where(Command.tenant_id == principal.tenant_id, Command.guardian_asset_id == principal.guardian_asset_id, Command.device_id == principal.device_id, Command.state == "queued", Command.expires_at > now).order_by(Command.created_at.asc()).limit(effective_limit).with_for_update(skip_locked=True)).scalars().all()
    acquired = []
    for command in candidates:
        token = secrets.token_urlsafe(32)
        lease_expires_at = min(command.expires_at, now + timedelta(seconds=LEASE_SECONDS))
        command.state = "dispatched"
        command.execution_token_hash = _hash_token(token)
        command.lease_expires_at = lease_expires_at
        command.dispatch_attempts += 1
        session.add(command_event("command.dispatched", command_id=command.command_id, tenant_id=command.tenant_id, asset_id=command.guardian_asset_id, device_id=command.device_id, occurred_at=now, extra={"lease_expires_at": lease_expires_at.isoformat(), "dispatch_attempts": command.dispatch_attempts}))
        acquired.append(AcquiredCommand(command.command_id, command.command_type, dict(command.arguments), token, lease_expires_at, command.expires_at))
    session.flush()
    return acquired
