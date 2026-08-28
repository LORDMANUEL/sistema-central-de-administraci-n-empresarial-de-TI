from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_CONTROL_", extra="ignore")
    database_url: str = "sqlite+pysqlite:///./agent-control.db"
    identity_jwks_url: str = "http://identity-service:8000/.well-known/jwks.json"
    identity_issuer: str = "urn:it-guardian:identity"
    identity_audience: str = "it-guardian-services"
    tenant_service_url: str = "http://tenant-service:8000"
    nats_url: str = "nats://nats:4222"
    nats_stream: str = "GUARDIAN_EVENTS"
    heartbeat_interval_seconds: int = 60
    command_poll_interval_seconds: int = 10
    offline_timeout_seconds: int = 180
    trusted_proxy_token: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
