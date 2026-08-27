from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
from app.schemas import CommandCreate
from app.service import ActorPrincipal, IdempotencyConflict, create_command


@dataclass(frozen=True)
class Fixture:
    tenant_id: UUID
    actor_id: UUID
    device_id: UUID
    asset_id: UUID


def command_request(fixture: Fixture, *, delay: int = 30, key: str = "idem-1") -> CommandCreate:
    return CommandCreate(
        device_id=fixture.device_id,
        guardian_asset_id=fixture.asset_id,
        command_type="device.reboot",
        arguments={"delay_seconds": delay},
        idempotency_key=key,
        expires_in_seconds=900,
    )


def test_same_idempotency_key_and_same_semantics_returns_same_command():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    fixture = Fixture(uuid4(), uuid4(), uuid4(), uuid4())
    actor = ActorPrincipal(fixture.tenant_id, fixture.actor_id)
    now = datetime.now(UTC)
    with Session(engine) as session:
        first = create_command(session, actor, command_request(fixture), now)
        second = create_command(session, actor, command_request(fixture), now)
        assert second.command_id == first.command_id
        assert second.request_digest == first.request_digest
        assert second.state == "queued"
    engine.dispose()


def test_same_idempotency_key_with_different_semantics_conflicts():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    fixture = Fixture(uuid4(), uuid4(), uuid4(), uuid4())
    actor = ActorPrincipal(fixture.tenant_id, fixture.actor_id)
    now = datetime.now(UTC)
    with Session(engine) as session:
        create_command(session, actor, command_request(fixture, delay=30), now)
        with pytest.raises(IdempotencyConflict):
            create_command(session, actor, command_request(fixture, delay=60), now)
    engine.dispose()


def test_same_idempotency_key_is_isolated_per_tenant():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    device_id = uuid4()
    asset_id = uuid4()
    key = "shared-key"
    now = datetime.now(UTC)
    with Session(engine) as session:
        tenant_a = ActorPrincipal(uuid4(), uuid4())
        tenant_b = ActorPrincipal(uuid4(), uuid4())
        request = CommandCreate(
            device_id=device_id,
            guardian_asset_id=asset_id,
            command_type="inventory.refresh",
            arguments={},
            idempotency_key=key,
            expires_in_seconds=900,
        )
        first = create_command(session, tenant_a, request, now)
        second = create_command(session, tenant_b, request, now)
        assert first.command_id != second.command_id
        assert first.tenant_id != second.tenant_id
    engine.dispose()
