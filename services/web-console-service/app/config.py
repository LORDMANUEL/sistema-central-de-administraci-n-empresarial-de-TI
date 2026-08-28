from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WEB_CONSOLE_", extra="ignore")

    gateway_url: str = "http://gateway-service:8000"
    session_cookie_name: str = "itg_session"
    session_ttl_seconds: int = Field(default=1800, ge=60, le=86400)
    max_sessions: int = Field(default=5000, ge=1, le=100000)
    cookie_secure: bool = True
    request_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
