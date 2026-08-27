from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,Field,model_validator

class CommandCreate(BaseModel):
    tenant_id: UUID | None = None
    device_id:UUID
    guardian_asset_id:UUID
    command_type:str=Field(min_length=1,max_length=64)
    arguments:dict=Field(default_factory=dict)
    idempotency_key:str=Field(min_length=1,max_length=128)
    expires_in_seconds:int=Field(ge=1,le=86400)

class CommandResultSubmit(BaseModel):
    execution_token:str=Field(min_length=16,max_length=512)
    result_sequence:int=Field(ge=1,le=2147483647)
    status:Literal["succeeded","failed"]
    exit_code:int|None=Field(default=None,ge=-2147483648,le=2147483647)
    summary:str=Field(default="",max_length=2048)
    started_at:datetime
    finished_at:datetime
    @model_validator(mode="after")
    def times(self):
        if self.finished_at<self.started_at:raise ValueError("finished_at must be >= started_at")
        return self

class RunningSubmit(BaseModel):
    execution_token:str=Field(min_length=16,max_length=512)

class CommandRead(BaseModel):
    command_id:UUID
    tenant_id:UUID
    guardian_asset_id:UUID
    device_id:UUID
    command_type:str
    arguments:dict
    state:str
    created_at:datetime
    expires_at:datetime
    dispatch_attempts:int
    lease_expires_at:datetime|None=None
    model_config={"from_attributes":True}
