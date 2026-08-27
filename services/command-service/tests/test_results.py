from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.acquire import acquire_commands
from app.models import Base
from app.principal import DevicePrincipal
from app.results import (
    CommandLeaseExpired,
    CommandStateConflict,
    ExecutionTokenInvalid,
    ResultConflict,
    mark_running,
    submit_result,
)
from app.schemas import CommandCreate, CommandResultSubmit
from app.service import ActorPrincipal, create_command


def make_command(session: Session, now: datetime):
    tenant_id, device_id, asset_id = uuid4(), uuid4(), uuid4()
    actor = ActorPrincipal(tenant_id, uuid4())
    command = create_command(
        session,
        actor,
        CommandCreate(
            device_id=device_id,
            guardian_asset_id=asset_id,
            command_type="inventory.refresh",
            arguments={},
            idempotency_key="result-test",
            expires_in_seconds=900,
        ),
        now,
    )
    principal = DevicePrincipal(tenant_id, asset_id, device_id, "01AB")
    acquired = acquire_commands(session, principal, now, limit=1)[0]
    return command, principal, acquired.execution_token


def success_result(token: str, now: datetime, *, summary: str = "inventory refreshed") -> CommandResultSubmit:
    return CommandResultSubmit(
        execution_token=token,
        result_sequence=1,
        status="succeeded",
        exit_code=0,
        summary=summary,
        started_at=now,
        finished_at=now + timedelta(seconds=1),
    )


def test_running_transition_is_idempotent():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        command, principal, token = make_command(session, now)
        first = mark_running(session, principal, command.command_id, token, now + timedelta(seconds=1))
        second = mark_running(session, principal, command.command_id, token, now + timedelta(seconds=2))
        assert first.state == "running"
        assert second.state == "running"
    engine.dispose()


def test_identical_terminal_result_replay_is_idempotent():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        command, principal, token = make_command(session, now)
        mark_running(session, principal, command.command_id, token, now + timedelta(seconds=1))
        payload = success_result(token, now + timedelta(seconds=1))
        first = submit_result(session, principal, command.command_id, payload, now + timedelta(seconds=3))
        second = submit_result(session, principal, command.command_id, payload, now + timedelta(seconds=4))
        assert second.result_id == first.result_id
        assert command.state == "succeeded"
    engine.dispose()


def test_conflicting_terminal_result_replay_is_rejected():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        command, principal, token = make_command(session, now)
        payload = success_result(token, now)
        submit_result(session, principal, command.command_id, payload, now + timedelta(seconds=2))
        changed = success_result(token, now, summary="different")
        with pytest.raises(ResultConflict):
            submit_result(session, principal, command.command_id, changed, now + timedelta(seconds=3))
    engine.dispose()


def test_wrong_execution_token_is_rejected():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        command, principal, _ = make_command(session, now)
        with pytest.raises(ExecutionTokenInvalid):
            mark_running(session, principal, command.command_id, "not-the-token", now + timedelta(seconds=1))
    engine.dispose()


def test_expired_lease_cannot_transition_running():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        command, principal, token = make_command(session, now)
        assert command.lease_expires_at is not None
        with pytest.raises(CommandLeaseExpired):
            mark_running(session, principal, command.command_id, token, command.lease_expires_at + timedelta(seconds=1))
    engine.dispose()


def test_terminal_command_cannot_change_to_another_result_sequence():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with Session(engine) as session:
        command, principal, token = make_command(session, now)
        submit_result(session, principal, command.command_id, success_result(token, now), now + timedelta(seconds=2))
        second_sequence = success_result(token, now).model_copy(update={"result_sequence": 2})
        with pytest.raises(CommandStateConflict):
            submit_result(session, principal, command.command_id, second_sequence, now + timedelta(seconds=3))
    engine.dispose()
