from __future__ import annotations

import threading
from dataclasses import dataclass
from time import monotonic
from typing import Any

import httpx
import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError

from .config import Settings
from .errors import GuardianError

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class IdentityPrincipal:
    user_id: str
    role: str


class AccessTokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cached: dict[str, Any] | None = None
        self._cached_at = 0.0
        self._lock = threading.Lock()

    def _jwks(self, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            age = monotonic() - self._cached_at
            if not force and self._cached is not None and age < self.settings.jwks_cache_seconds:
                return self._cached
            try:
                response = httpx.get(self.settings.identity_jwks_url, timeout=5.0)
                response.raise_for_status()
                jwks = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise GuardianError(503, "asset.identity_unavailable", "Identity public keys are unavailable") from exc
            if not isinstance(jwks, dict) or not isinstance(jwks.get("keys"), list):
                raise GuardianError(503, "asset.identity_invalid_jwks", "Identity public key response is invalid")
            self._cached = jwks
            self._cached_at = monotonic()
            return jwks

    def verify(self, token: str) -> IdentityPrincipal:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not isinstance(kid, str) or not kid:
                raise GuardianError(401, "asset.invalid_token", "Invalid access token")
            key = None
            for force in (False, True):
                for item in self._jwks(force=force).get("keys", []):
                    if item.get("kid") == kid:
                        key = jwt.PyJWK.from_dict(item).key
                        break
                if key is not None:
                    break
            if key is None:
                raise GuardianError(401, "asset.unknown_signing_key", "Unknown Identity signing key")
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
            raise GuardianError(401, "asset.token_expired", "Access token has expired") from exc
        except (InvalidTokenError, ValueError) as exc:
            raise GuardianError(401, "asset.invalid_token", "Invalid access token") from exc

        if claims.get("type") != "access":
            raise GuardianError(401, "asset.invalid_token_type", "Access token is required")
        return IdentityPrincipal(user_id=str(claims["sub"]), role=str(claims["role"]))


def current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> IdentityPrincipal:
    if getattr(request.app.state, "auth_disabled", False):
        return IdentityPrincipal(user_id="test-platform-admin", role="platform_admin")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise GuardianError(401, "asset.authentication_required", "Authentication is required")
    return request.app.state.auth.verify(credentials.credentials)


def require_platform_admin(principal: IdentityPrincipal = Depends(current_principal)) -> IdentityPrincipal:
    if principal.role != "platform_admin":
        raise GuardianError(403, "asset.platform_admin_required", "Platform administrator role is required")
    return principal
