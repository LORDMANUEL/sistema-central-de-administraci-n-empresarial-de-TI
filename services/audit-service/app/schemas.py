from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditRecordResponse(BaseModel):
    id: str
    tenant_id: str | None
    sequence: int
    chain_key: str
    source_event_id: str
    source_type: str
    source_service: str
    actor_user_id: str | None
    actor_type: str
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    request_id: str | None
    occurred_at: datetime
    ingested_at: datetime
    metadata: dict[str, Any]
    prev_hash: str
    record_hash: str


class AuditRecordListResponse(BaseModel):
    items: list[AuditRecordResponse]
    next_after_sequence: int | None = None


class AuditChainVerificationResponse(BaseModel):
    chain_key: str
    valid: bool
    record_count: int
    last_sequence: int
    last_hash: str
    first_invalid_sequence: int | None = None
    first_invalid_record_id: str | None = None
