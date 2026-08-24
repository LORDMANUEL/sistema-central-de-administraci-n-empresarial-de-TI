from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ENROLLMENT_", env_file=".env", extra="ignore")

    service_name: str = "enrollment-service"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://guardian:change-me@postgres:5432/guardian_enrollment"

    signing_key: str = ""
    jwt_key_id: str = "enrollment-ed25519-v1"
    jwt_issuer: str = "urn:it-guardian:enrollment"
    pki_audience: str = "it-guardian-pki"
    grant_lifetime_seconds: int = Field(default=60, ge=30, le=120)

    token_default_ttl_minutes: int = Field(default=60, ge=5, le=1440)
    token_min_ttl_minutes: int = Field(default=5, ge=1, le=1440)
    token_max_ttl_minutes: int = Field(default=1440, ge=5, le=10080)

    identity_jwks_url: str = "http://identity-service:8000/.well-known/jwks.json"
    identity_issuer: str = "urn:it-guardian:identity"
    identity_audience: str = "it-guardian-services"
    jwks_cache_seconds: int = Field(default=300, ge=1, le=3600)

    tenant_service_url: str = "http://tenant-service:8000"
    asset_service_url: str = "http://asset-service:8000"
    pki_service_url: str = "http://pki-service:8000"
    downstream_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    pki_retry_attempts: int = Field(default=3, ge=1, le=5)

    nats_url: str = "nats://nats:4222"
    nats_stream: str = "GUARDIAN_EVENTS"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
