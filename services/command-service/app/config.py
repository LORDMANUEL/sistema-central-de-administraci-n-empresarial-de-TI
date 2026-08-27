from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_prefix="COMMAND_",extra="ignore")
    database_url:str="sqlite+pysqlite:///./command.db"
    identity_jwks_url:str="http://identity-service:8000/.well-known/jwks.json"
    identity_issuer:str="urn:it-guardian:identity"
    identity_audience:str="it-guardian-services"
    asset_service_url:str="http://asset-service:8000"
    agent_control_service_url:str="http://agent-control-service:8000"
    trusted_proxy_token:str=""
    nats_url:str="nats://nats:4222"
    nats_stream:str="GUARDIAN_EVENTS"
    wake_stream:str="GUARDIAN_COMMAND_WAKE"

@lru_cache
def get_settings(): return Settings()
