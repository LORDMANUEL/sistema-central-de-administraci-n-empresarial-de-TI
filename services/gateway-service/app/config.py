from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GATEWAY_", env_file=".env", extra="ignore")

    service_name: str = "gateway-service"
    environment: str = "development"

    identity_service_url: str = "http://identity-service:8000"
    tenant_service_url: str = "http://tenant-service:8000"
    asset_service_url: str = "http://asset-service:8000"
    enrollment_service_url: str = "http://enrollment-service:8000"
    pki_service_url: str = "http://pki-service:8000"
    audit_service_url: str = "http://audit-service:8000"
    agent_control_service_url: str = "http://agent-control-service:8000"
    command_service_url: str = "http://command-service:8000"
    telemetry_service_url: str = "http://telemetry-service:8000"

    identity_jwks_url: str = "http://identity-service:8000/.well-known/jwks.json"
    identity_issuer: str = "urn:it-guardian:identity"
    identity_audience: str = "it-guardian-services"
    jwks_cache_seconds: int = Field(default=300, ge=1, le=3600)

    nats_url: str = "nats://nats:4222"
    nats_stream: str = "GUARDIAN_EVENTS"
    nats_connect_timeout_seconds: float = Field(default=3.0, gt=0, le=15)

    default_max_body_bytes: int = Field(default=1024 * 1024, ge=1024, le=16 * 1024 * 1024)
    default_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    max_request_id_length: int = Field(default=128, ge=16, le=256)
    max_header_bytes: int = Field(default=32 * 1024, ge=4096, le=256 * 1024)
