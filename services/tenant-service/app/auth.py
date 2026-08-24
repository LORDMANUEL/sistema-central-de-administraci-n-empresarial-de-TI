from __future__ import annotations

import threading
from dataclasses import dataclass
from time import monotonic
from typing import Any

import httpx
import jwt
from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError

from .config import Settings
from .errors import GuardianError

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class IdentityPrincipal:
    user_id: str
    role: str


class JwksProvider:
    def __init__(self, settings: Settings, static_jwks: dict[str, Any] | None = None) -> None:
        self.settings = settings
        self.static_jwks = static_jwks
        self._cached: dict[str, Any] | None = static_jwks
        self._cached_at = monotonic() if static_jwks is not None else 0.0
        self._lock = threading.Lock()

    def get(self, *, force: bool = False) -> dict[str, Any]:
        if self.static_jwks is not None:
            return self.static_jwks
        with self._lock:
            age = monotonic() - self._cached_at
            if not force and self._cached is not None and age < self.settings.jwks_cache_seconds:
                return self._cached
            try:
                response = httpx.get(self.settings.identity_jwks_url, timeout=5.0)
                response.raise_for_status()
                jwks = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise GuardianError(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "tenant.identity_unavailable",
                    "Identity public keys are unavailable",
                ) from exc
            if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
                raise GuardianError(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "tenant.identity_invalid_jwks",
                    "Identity public key response is invalid",
                )
            self._cached = jwks
            self._cached_at = monotonic()
            return jwks


class AccessTokenVerifier:
    def __init__(self, settings: Settings, static_jwks: dict[str, Any] | None = None) -> None:
        self.settings = settings
        self.provider = JwksProvider(settings, static_jwks)

    def _key_for(self, kid: str) -> Any:
        for force in (False, True):
            jwks = self.provider.get(force=force)
            for item in jwks.get("keys", []):
                if item.get("kid") == kid:
                    try:
                        return jwt.PyJWK.from_dict(item).key
                    except (InvalidTokenError, ValueError) as exc:
                        raise GuardianError(401, "tenant.invalid_token", "Invalid access token") from exc
            if self.provider.static_jwks is not None:
                break
        raise GuardianError(401, "tenant.unknown_signing_key", "Unknown Identity signing key")

    def verify(self, token: str) -> IdentityPrincipal:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not isinstance(kid, str) or not kid:
                raise GuardianError(401, "tenant.invalid_token", "Invalid access token")
            key = self._key_for(kid)
            claims = jwt.decode(
                token,
                key,
                algorithms=["EdDSA"],
                issuer=self.settings.identity_issuer,
                audience=self.settings.identity_audience,
                options={"require": ["sub", "role", "type", "iss", "aud", "iat", "exp", "jti"]},
            )
        except GuardianError:
            raise
        except ExpiredSignatureError as exc:
            raise GuardianError(401, "tenant.token_expired", "Access token has expired") from exc
        except InvalidTokenError as exc:
            raise GuardianError(401, "tenant.invalid_token", "Invalid access token") from exc

        if claims.get("type") != "access":
            raise GuardianError(401, "tenant.invalid_token_type", "Access token is required")
        role = claims.get("role")
        user_id = claims.get("sub")
        if not isinstance(role, str) or not isinstance(user_id, str):
            raise GuardianError(401, "tenant.invalid_token", "Invalid access token")
        return IdentityPrincipal(user_id=user_id, role=role)


def current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> IdentityPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise GuardianError(401, "tenant.authentication_required", "Authentication is required")
    return request.app.state.auth.verify(credentials.credentials)


def require_platform_admin(principal: IdentityPrincipal = Depends(current_principal)) -> IdentityPrincipal:
    if principal.role != "platform_admin":
        raise GuardianError(403, "tenant.platform_admin_required", "Platform administrator role is required")
    return principal
