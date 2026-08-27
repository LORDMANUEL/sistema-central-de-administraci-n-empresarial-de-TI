from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TelemetrySampleInput(BaseModel):
    metric: str = Field(min_length=1, max_length=96)
    value: int | float
    labels: dict[str, str] = Field(default_factory=dict)
    observed_at: datetime


class TelemetryBatchInput(BaseModel):
    batch_id: UUID
    sent_at: datetime
    samples: list[TelemetrySampleInput] = Field(min_length=1, max_length=256)
