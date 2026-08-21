from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
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


def _create_token(user: User, settings: Settings, token_type: TokenType) -> str:
    now = datetime.now(UTC)
    if token_type == "access":
        expires_at = now + timedelta(minutes=settings.access_token_minutes)
    else:
        expires_at = now + timedelta(days=settings.refresh_token_days)

    payload = {
        "sub": user.id,
        "role": user.role.value,
        "type": token_type,
        "iat": now,
        "exp": expires_at,
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")


def create_access_token(user: User, settings: Settings) -> str:
    return _create_token(user, settings, "access")


def create_refresh_token(user: User, settings: Settings) -> str:
    return _create_token(user, settings, "refresh")


def decode_token(token: str, settings: Settings, expected_type: TokenType) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            options={"require": ["sub", "role", "type", "iat", "exp", "jti"]},
        )
    except ExpiredSignatureError as exc:
        raise GuardianError(401, "identity.token_expired", "Token has expired") from exc
    except InvalidTokenError as exc:
        raise GuardianError(401, "identity.invalid_token", "Invalid token") from exc

    if payload.get("type") != expected_type:
        raise GuardianError(401, "identity.invalid_token_type", "Invalid token type")
    return payload


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

    claims = decode_token(credentials.credentials, request.app.state.settings, "access")
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
