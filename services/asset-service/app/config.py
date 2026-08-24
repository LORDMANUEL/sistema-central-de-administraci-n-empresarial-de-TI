from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "asset-service"
    environment: str = "development"
    database_url: str = "sqlite+pysqlite:///./asset.db"
    identity_jwks_url: str = "http://identity-service:8000/.well-known/jwks.json"
    identity_issuer: str = "urn:it-guardian:identity"
    identity_audience: str = "it-guardian-services"
    jwks_cache_seconds: int = 300
    tenant_service_url: str = "http://tenant-service:8000"
    tenant_access_timeout_seconds: float = 5.0
    nats_url: str = "nats://nats:4222"
    nats_stream: str = "GUARDIAN_EVENTS"

    model_config = SettingsConfigDict(env_prefix="ASSET_", env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
