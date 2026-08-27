from uuid import UUID

from pydantic import BaseModel, Field


class CommandCreate(BaseModel):
    device_id: UUID
    guardian_asset_id: UUID
    command_type: str = Field(min_length=1, max_length=64)
    arguments: dict = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=128)
    expires_in_seconds: int = Field(ge=1, le=86400)
