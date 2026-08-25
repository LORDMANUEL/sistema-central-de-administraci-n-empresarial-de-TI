from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUDIT_", env_file=".env", extra="ignore")

    service_name: str = "audit-service"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://guardian:change-me@postgres:5432/guardian_audit"

    identity_jwks_url: str = "http://identity-service:8000/.well-known/jwks.json"
    identity_issuer: str = "urn:it-guardian:identity"
    identity_audience: str = "it-guardian-services"
    jwks_cache_seconds: int = Field(default=300, ge=1, le=3600)

    tenant_service_url: str = "http://tenant-service:8000"
    downstream_timeout_seconds: float = Field(default=5.0, gt=0, le=30)

    nats_url: str = "nats://nats:4222"
    nats_stream: str = "GUARDIAN_EVENTS"
    nats_durable: str = "guardian-audit-v1"
    consumer_batch_size: int = Field(default=100, ge=1, le=500)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
