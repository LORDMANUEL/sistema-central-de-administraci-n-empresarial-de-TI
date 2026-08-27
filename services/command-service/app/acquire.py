from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    return sha256(token.encode("utf-8")).hexdigest()


def acquire_commands(
    session: Session,
    principal: DevicePrincipal,
    now: datetime,
    *,
    limit: int = MAX_ACQUIRE_LIMIT,
) -> list[AcquiredCommand]:
    effective_limit = max(0, min(limit, MAX_ACQUIRE_LIMIT))
    if effective_limit == 0:
        return []

    expired = session.execute(
        select(Command)
        .where(
            Command.tenant_id == principal.tenant_id,
            Command.guardian_asset_id == principal.guardian_asset_id,
            Command.device_id == principal.device_id,
            Command.state == "queued",
            Command.expires_at <= now,
        )
        .with_for_update()
    ).scalars().all()
    for command in expired:
        command.state = "expired"

    candidates = session.execute(
        select(Command)
        .where(
            Command.tenant_id == principal.tenant_id,
            Command.guardian_asset_id == principal.guardian_asset_id,
            Command.device_id == principal.device_id,
            Command.state == "queued",
            Command.expires_at > now,
        )
        .order_by(Command.created_at.asc(), Command.command_id.asc())
        .limit(effective_limit)
        .with_for_update(skip_locked=True)
    ).scalars().all()

    acquired: list[AcquiredCommand] = []
    for command in candidates:
        token = secrets.token_urlsafe(32)
        lease_expires_at = min(command.expires_at, now + timedelta(seconds=LEASE_SECONDS))
        command.state = "dispatched"
        command.execution_token_hash = _hash_token(token)
        command.lease_expires_at = lease_expires_at
        command.dispatch_attempts += 1
        acquired.append(
            AcquiredCommand(
                command_id=command.command_id,
                command_type=command.command_type,
                arguments=dict(command.arguments),
                execution_token=token,
                lease_expires_at=lease_expires_at,
                expires_at=command.expires_at,
            )
        )

    session.flush()
    return acquired
