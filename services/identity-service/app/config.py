from functools import lru_cache

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DEVELOPMENT_JWT_SECRET = "development-only-change-me-32-characters"


class Settings(BaseSettings):
    service_name: str = "identity-service"
    environment: str = "development"
    database_url: str = "sqlite+pysqlite:///./identity.db"
    jwt_secret: SecretStr = SecretStr(DEFAULT_DEVELOPMENT_JWT_SECRET)
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    model_config = SettingsConfigDict(
        env_prefix="IDENTITY_",
        env_file=".env",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        secret = self.jwt_secret.get_secret_value()
        if len(secret) < 32:
            raise ValueError("IDENTITY_JWT_SECRET must contain at least 32 characters")
        if self.environment.lower() == "production" and secret == DEFAULT_DEVELOPMENT_JWT_SECRET:
            raise ValueError("Production cannot use the development JWT secret")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
