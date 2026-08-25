from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select

from .auth import IdentityPrincipal, current_principal, enforce_audit_read
from .chain import verify_chain
from .errors import GuardianError
from .models import AuditRecord
from .schemas import AuditChainVerificationResponse, AuditRecordListResponse, AuditRecordResponse

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


def _record_response(record: AuditRecord) -> AuditRecordResponse:
    return AuditRecordResponse(
        id=record.id,
        tenant_id=record.tenant_id,
        sequence=record.sequence,
        chain_key=record.chain_key,
        source_event_id=record.source_event_id,
        source_type=record.source_type,
        source_service=record.source_service,
        actor_user_id=record.actor_user_id,
        actor_type=record.actor_type,
        action=record.action,
        resource_type=record.resource_type,
        resource_id=record.resource_id,
        outcome=record.outcome,
        request_id=record.request_id,
        occurred_at=record.occurred_at,
        ingested_at=record.ingested_at,
        metadata=record.metadata_json,
        prev_hash=record.prev_hash,
        record_hash=record.record_hash,
    )


def _authorize(request: Request, principal: IdentityPrincipal, tenant_id: str | None) -> None:
    enforce_audit_read(
        principal,
        tenant_id,
        request.app.state.tenant_access_client.resolve,
    )


@router.get("/records", response_model=AuditRecordListResponse)
def list_records(
    request: Request,
    tenant_id: str | None = Query(default=None),
    after_sequence: int | None = Query(default=None, ge=0),
    source_type: str | None = Query(default=None),
    actor_user_id: str | None = Query(default=None),
    action: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=100, ge=1, le=500),
    principal: IdentityPrincipal = Depends(current_principal),
) -> AuditRecordListResponse:
    _authorize(request, principal, tenant_id)
    if tenant_id is None and after_sequence is not None:
        raise GuardianError(400, "audit.sequence_cursor_requires_tenant", "Sequence cursor requires tenant scope")

    statement = select(AuditRecord)
    if tenant_id is not None:
        statement = statement.where(AuditRecord.tenant_id == tenant_id)
        if after_sequence is not None:
            statement = statement.where(AuditRecord.sequence > after_sequence)
    if source_type:
        statement = statement.where(AuditRecord.source_type == source_type)
    if actor_user_id:
        statement = statement.where(AuditRecord.actor_user_id == actor_user_id)
    if action:
        statement = statement.where(AuditRecord.action == action)
    if resource_type:
        statement = statement.where(AuditRecord.resource_type == resource_type)
    if resource_id:
        statement = statement.where(AuditRecord.resource_id == resource_id)
    if outcome:
        statement = statement.where(AuditRecord.outcome == outcome)
    if request_id:
        statement = statement.where(AuditRecord.request_id == request_id)
    if from_time:
        statement = statement.where(AuditRecord.occurred_at >= from_time)
    if to_time:
        statement = statement.where(AuditRecord.occurred_at <= to_time)

    if tenant_id is not None:
        statement = statement.order_by(AuditRecord.sequence.asc())
    else:
        statement = statement.order_by(AuditRecord.occurred_at.desc(), AuditRecord.id.desc())
    statement = statement.limit(limit)

    with request.app.state.session_factory() as session:
        records = list(session.scalars(statement))

    next_after = records[-1].sequence if tenant_id is not None and records else None
    return AuditRecordListResponse(
        items=[_record_response(record) for record in records],
        next_after_sequence=next_after,
    )


@router.get("/records/{record_id}", response_model=AuditRecordResponse)
def get_record(
    record_id: str,
    request: Request,
    principal: IdentityPrincipal = Depends(current_principal),
) -> AuditRecordResponse:
    with request.app.state.session_factory() as session:
        record = session.get(AuditRecord, record_id)
        if record is None:
            raise GuardianError(404, "audit.record_not_found", "Audit record not found")
        _authorize(request, principal, record.tenant_id)
        return _record_response(record)


@router.get("/verify", response_model=AuditChainVerificationResponse)
def verify_audit_chain(
    request: Request,
    tenant_id: str | None = Query(default=None),
    principal: IdentityPrincipal = Depends(current_principal),
) -> AuditChainVerificationResponse:
    _authorize(request, principal, tenant_id)
    chain_key = f"tenant:{tenant_id}" if tenant_id else "platform"
    with request.app.state.session_factory() as session:
        result = verify_chain(session, chain_key)
    return AuditChainVerificationResponse(
        chain_key=chain_key,
        valid=result.valid,
        record_count=result.record_count,
        last_sequence=result.last_sequence,
        last_hash=result.last_hash,
        first_invalid_sequence=result.first_invalid_sequence,
        first_invalid_record_id=result.first_invalid_record_id,
    )
