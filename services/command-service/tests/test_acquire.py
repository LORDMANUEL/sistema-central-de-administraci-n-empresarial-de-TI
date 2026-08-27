from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.acquire import acquire_commands
from app.models import Base
from app.principal import DevicePrincipal
from app.schemas import CommandCreate
from app.service import ActorPrincipal, create_command


def request(device_id, asset_id, *, key: str) -> CommandCreate:
    return CommandCreate(
        device_id=device_id,
        guardian_asset_id=asset_id,
        command_type="inventory.refresh",
        arguments={},
        idempotency_key=key,
        expires_in_seconds=900,
    )


def test_device_acquires_only_commands_bound_to_its_identity():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tenant_id = uuid4()
    device_a, device_b = uuid4(), uuid4()
    asset_a, asset_b = uuid4(), uuid4()
    actor = ActorPrincipal(tenant_id, uuid4())
    principal_a = DevicePrincipal(tenant_id, asset_a, device_a, "01AB")
    now = datetime.now(UTC)

    with Session(engine) as session:
        command_a = create_command(session, actor, request(device_a, asset_a, key="a"), now)
        command_b = create_command(session, actor, request(device_b, asset_b, key="b"), now)

        acquired = acquire_commands(session, principal_a, now, limit=10)

        assert [item.command_id for item in acquired] == [command_a.command_id]
        assert command_a.state == "dispatched"
        assert command_a.execution_token_hash is not None
        assert command_a.lease_expires_at is not None
        assert command_a.dispatch_attempts == 1
        assert command_b.state == "queued"
        assert acquired[0].execution_token
        assert acquired[0].execution_token not in command_a.execution_token_hash
    engine.dispose()


def test_acquisition_is_oldest_first_and_respects_limit():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tenant_id, device_id, asset_id = uuid4(), uuid4(), uuid4()
    actor = ActorPrincipal(tenant_id, uuid4())
    principal = DevicePrincipal(tenant_id, asset_id, device_id, "01AB")
    now = datetime.now(UTC)

    with Session(engine) as session:
        first = create_command(session, actor, request(device_id, asset_id, key="first"), now)
        second = create_command(session, actor, request(device_id, asset_id, key="second"), now)
        acquired = acquire_commands(session, principal, now, limit=1)

        assert len(acquired) == 1
        assert acquired[0].command_id == first.command_id
        assert first.state == "dispatched"
        assert second.state == "queued"
    engine.dispose()


def test_expired_command_is_not_dispatched():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tenant_id, device_id, asset_id = uuid4(), uuid4(), uuid4()
    actor = ActorPrincipal(tenant_id, uuid4())
    principal = DevicePrincipal(tenant_id, asset_id, device_id, "01AB")
    created_at = datetime(2026, 8, 27, 0, 0, tzinfo=UTC)

    with Session(engine) as session:
        command = create_command(
            session,
            actor,
            CommandCreate(
                device_id=device_id,
                guardian_asset_id=asset_id,
                command_type="inventory.refresh",
                arguments={},
                idempotency_key="expired",
                expires_in_seconds=1,
            ),
            created_at,
        )
        acquired = acquire_commands(session, principal, datetime(2026, 8, 27, 0, 1, tzinfo=UTC), limit=10)

        assert acquired == []
        assert command.state == "expired"
    engine.dispose()
