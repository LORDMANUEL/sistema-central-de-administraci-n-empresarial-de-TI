from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PKI_", env_file=".env", extra="ignore")

    service_name: str = "pki-service"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://guardian:change-me@postgres:5432/guardian_pki"

    ca_cert_path: str = "/var/lib/guardian/pki/intermediate-ca-cert.pem"
    ca_key_path: str = "/var/lib/guardian/pki/intermediate-ca-key.pem"
    root_cert_path: str = "/var/lib/guardian/pki/root-ca-cert.pem"

    certificate_lifetime_days: int = Field(default=30, ge=1, le=90)
    clock_skew_seconds: int = Field(default=120, ge=0, le=600)
    crl_lifetime_hours: int = Field(default=24, ge=1, le=168)
    grant_max_lifetime_seconds: int = Field(default=120, ge=30, le=300)

    identity_jwks_url: str = "http://identity-service:8000/.well-known/jwks.json"
    identity_issuer: str = "urn:it-guardian:identity"
    identity_audience: str = "it-guardian"
    enrollment_jwks_url: str = "http://enrollment-service:8000/.well-known/jwks.json"
    enrollment_issuer: str = "urn:it-guardian:enrollment"
    enrollment_audience: str = "it-guardian-pki"
    jwks_cache_seconds: int = Field(default=300, ge=1, le=3600)

    tenant_service_url: str = "http://tenant-service:8000"
    tenant_access_timeout_seconds: float = Field(default=5.0, gt=0, le=30)

    nats_url: str = "nats://nats:4222"
    nats_stream: str = "GUARDIAN_EVENTS"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
