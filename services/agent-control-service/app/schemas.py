from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class HeartbeatInput(BaseModel):
    session_id: UUID
    agent_version: str = Field(min_length=1, max_length=128)
    platform: str = Field(min_length=1, max_length=128)
    platform_version: str = Field(min_length=1, max_length=128)
    capabilities: list[str] = Field(default_factory=list, max_length=128)
    capability_version: int = Field(ge=1)
    sent_at: datetime

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value or len(value) > 96:
                raise ValueError("capability must contain 1..96 characters")
        return values
