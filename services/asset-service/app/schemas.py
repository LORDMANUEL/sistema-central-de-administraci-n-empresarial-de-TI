from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssetCreate(BaseModel):
    tenant_id: str = Field(min_length=36, max_length=36)
    site_id: str | None = Field(default=None, min_length=36, max_length=36)
    department_id: str | None = Field(default=None, min_length=36, max_length=36)
    asset_type: str = Field(min_length=2, max_length=32)
    display_name: str = Field(min_length=1, max_length=255)
    hostname: str | None = Field(default=None, max_length=255)
    serial_number: str | None = Field(default=None, max_length=255)


class AssetRead(BaseModel):
    guardian_asset_id: str
    tenant_id: str
    site_id: str | None
    department_id: str | None
    asset_type: str
    display_name: str
    hostname: str | None
    serial_number: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExternalIdentityCreate(BaseModel):
    provider: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    external_id: str = Field(min_length=1, max_length=255)


class ExternalIdentityRead(BaseModel):
    id: str
    guardian_asset_id: str
    provider: str
    external_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
