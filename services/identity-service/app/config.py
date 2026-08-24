import base64
import binascii
from functools import lru_cache

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DEVELOPMENT_SIGNING_KEY = "aXQtZ3VhcmRpYW4tZGV2LWVkMjU1MTktc2VlZC12MSE"


def decode_signing_seed(value: str) -> bytes:
    try:
        padding = "=" * (-len(value) % 4)
        seed = base64.urlsafe_b64decode(value + padding)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("IDENTITY_SIGNING_KEY must be URL-safe base64") from exc
    if len(seed) != 32:
        raise ValueError("IDENTITY_SIGNING_KEY must decode to exactly 32 bytes")
    return seed


class Settings(BaseSettings):
    service_name: str = "identity-service"
    environment: str = "development"
    database_url: str = "sqlite+pysqlite:///./identity.db"
    signing_key: SecretStr = SecretStr(DEFAULT_DEVELOPMENT_SIGNING_KEY)
    jwt_key_id: str = "identity-ed25519-v1"
    jwt_issuer: str = "urn:it-guardian:identity"
    jwt_audience: str = "it-guardian-services"
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    model_config = SettingsConfigDict(
        env_prefix="IDENTITY_",
        env_file=".env",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        key_value = self.signing_key.get_secret_value()
        decode_signing_seed(key_value)
        if self.environment.lower() == "production" and key_value == DEFAULT_DEVELOPMENT_SIGNING_KEY:
            raise ValueError("Production cannot use the development signing key")
        if not self.jwt_key_id.strip():
            raise ValueError("IDENTITY_JWT_KEY_ID cannot be empty")
        if not self.jwt_issuer.strip():
            raise ValueError("IDENTITY_JWT_ISSUER cannot be empty")
        if not self.jwt_audience.strip():
            raise ValueError("IDENTITY_JWT_AUDIENCE cannot be empty")
        return self

    @property
    def signing_seed(self) -> bytes:
        return decode_signing_seed(self.signing_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
