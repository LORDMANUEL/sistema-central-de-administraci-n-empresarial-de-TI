from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class CommandCreate(BaseModel):
    device_id: UUID
    guardian_asset_id: UUID
    command_type: str = Field(min_length=1, max_length=64)
    arguments: dict = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=1, max_length=128)
    expires_in_seconds: int = Field(ge=1, le=86400)


class CommandResultSubmit(BaseModel):
    execution_token: str = Field(min_length=16, max_length=512)
    result_sequence: int = Field(ge=1, le=2_147_483_647)
    status: Literal["succeeded", "failed"]
    exit_code: int | None = Field(default=None, ge=-2_147_483_648, le=2_147_483_647)
    summary: str = Field(default="", max_length=2048)
    started_at: datetime
    finished_at: datetime

    @model_validator(mode="after")
    def validate_result_times(self):
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must be greater than or equal to started_at")
        return self
