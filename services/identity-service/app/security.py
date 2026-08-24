import base64
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from sqlalchemy.orm import Session

from .config import Settings
from .database import get_db
from .errors import GuardianError
from .models import Role, User

_password_hasher = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)
TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class TokenService:
    algorithm = "EdDSA"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.private_key = Ed25519PrivateKey.from_private_bytes(settings.signing_seed)
        self.public_key = self.private_key.public_key()

    def _create(self, user: User, token_type: TokenType) -> str:
        now = datetime.now(UTC)
        if token_type == "access":
            expires_at = now + timedelta(minutes=self.settings.access_token_minutes)
        else:
            expires_at = now + timedelta(days=self.settings.refresh_token_days)

        payload = {
            "sub": user.id,
            "role": user.role.value,
            "type": token_type,
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.jwt_audience,
            "iat": now,
            "exp": expires_at,
            "jti": str(uuid4()),
        }
        return jwt.encode(
            payload,
            self.private_key,
            algorithm=self.algorithm,
            headers={"kid": self.settings.jwt_key_id, "typ": "JWT"},
        )

    def create_access_token(self, user: User) -> str:
        return self._create(user, "access")

    def create_refresh_token(self, user: User) -> str:
        return self._create(user, "refresh")

    def decode(self, token: str, expected_type: TokenType) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("kid") != self.settings.jwt_key_id:
                raise GuardianError(401, "identity.unknown_signing_key", "Unknown signing key")
            payload = jwt.decode(
                token,
                self.public_key,
                algorithms=[self.algorithm],
                issuer=self.settings.jwt_issuer,
                audience=self.settings.jwt_audience,
                options={
                    "require": ["sub", "role", "type", "iss", "aud", "iat", "exp", "jti"]
                },
            )
        except GuardianError:
            raise
        except ExpiredSignatureError as exc:
            raise GuardianError(401, "identity.token_expired", "Token has expired") from exc
        except InvalidTokenError as exc:
            raise GuardianError(401, "identity.invalid_token", "Invalid token") from exc

        if payload.get("type") != expected_type:
            raise GuardianError(401, "identity.invalid_token_type", "Invalid token type")
        return payload

    def jwks(self) -> dict[str, list[dict[str, str]]]:
        raw_public_key = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return {
            "keys": [
                {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "x": _b64url(raw_public_key),
                    "use": "sig",
                    "alg": self.algorithm,
                    "kid": self.settings.jwt_key_id,
                }
            ]
        }


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise GuardianError(
            status.HTTP_401_UNAUTHORIZED,
            "identity.authentication_required",
            "Authentication is required",
        )

    claims = request.app.state.tokens.decode(credentials.credentials, "access")
    user = session.get(User, claims["sub"])
    if user is None:
        raise GuardianError(
            status.HTTP_401_UNAUTHORIZED,
            "identity.invalid_token",
            "Invalid token",
        )
    if not user.is_active:
        raise GuardianError(
            status.HTTP_403_FORBIDDEN,
            "identity.user_disabled",
            "User account is disabled",
        )
    return user


def require_roles(*allowed_roles: Role):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise GuardianError(
                status.HTTP_403_FORBIDDEN,
                "identity.forbidden",
                "You do not have permission to perform this action",
            )
        return user

    return dependency
