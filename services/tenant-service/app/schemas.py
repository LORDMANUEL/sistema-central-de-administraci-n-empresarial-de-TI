import re
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import DepartmentStatus, MembershipRole, SiteStatus, TenantStatus

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
LOCALE_RE = re.compile(r"^[a-zA-Z]{2,3}(?:-[a-zA-Z]{2})?$")


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Unknown IANA timezone") from exc
    return value


class TenantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=2, max_length=64)
    timezone: str
    locale: str = Field(default="es-HN", max_length=16)

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value: str) -> str:
        value = value.strip().lower()
        if not SLUG_RE.fullmatch(value):
            raise ValueError("Slug may contain lowercase letters, digits and internal hyphens")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        return validate_timezone(value)

    @field_validator("locale")
    @classmethod
    def valid_locale(cls, value: str) -> str:
        if not LOCALE_RE.fullmatch(value):
            raise ValueError("Locale must look like es or es-HN")
        return value


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    status: TenantStatus | None = None
    timezone: str | None = None
    locale: str | None = Field(default=None, max_length=16)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        return validate_timezone(value) if value is not None else None

    @field_validator("locale")
    @classmethod
    def valid_locale(cls, value: str | None) -> str | None:
        if value is not None and not LOCALE_RE.fullmatch(value):
            raise ValueError("Locale must look like es or es-HN")
        return value


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    status: TenantStatus
    timezone: str
    locale: str
    created_at: datetime
    updated_at: datetime


class MembershipUpsert(BaseModel):
    user_id: UUID
    role: MembershipRole


class MembershipUpdate(BaseModel):
    role: MembershipRole | None = None
    is_active: bool | None = None


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    user_id: str
    role: MembershipRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


CODE_RE = re.compile(r"^[A-Z0-9](?:[A-Z0-9_-]{0,30}[A-Z0-9])?$")


def normalize_code(value: str) -> str:
    value = value.strip().upper()
    if not CODE_RE.fullmatch(value):
        raise ValueError("Code may contain letters, digits, underscores and internal hyphens")
    return value


class SiteCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=2, max_length=160)
    timezone: str | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    address_line1: str | None = Field(default=None, max_length=240)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return normalize_code(value)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        return validate_timezone(value) if value is not None else None

    @field_validator("country_code")
    @classmethod
    def valid_country(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if not value.isalpha():
            raise ValueError("country_code must contain two letters")
        return value


class SiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    status: SiteStatus | None = None
    timezone: str | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    address_line1: str | None = Field(default=None, max_length=240)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        return validate_timezone(value) if value is not None else None

    @field_validator("country_code")
    @classmethod
    def valid_country(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.upper()
        if not value.isalpha():
            raise ValueError("country_code must contain two letters")
        return value


class SiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    code: str
    name: str
    status: SiteStatus
    timezone: str | None
    country_code: str | None
    region: str | None
    city: str | None
    address_line1: str | None
    latitude: float | None
    longitude: float | None
    created_at: datetime
    updated_at: datetime


class DepartmentCreate(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=160)
    parent_id: UUID | None = None

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return normalize_code(value)


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    status: DepartmentStatus | None = None
    parent_id: UUID | None = None


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    code: str
    name: str
    status: DepartmentStatus
    parent_id: str | None
    created_at: datetime
    updated_at: datetime
