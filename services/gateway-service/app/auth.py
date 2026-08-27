from __future__ import annotations

import threading
from dataclasses import dataclass
from time import monotonic
from typing import Any

import httpx
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from .config import Settings
from .errors import GatewayError


@dataclass(frozen=True)
class IdentityPrincipal:
    user_id: str
    role: str
    bearer_token: str


class IdentityAccessVerifier:
    def __init__(self, settings: Settings, *, jwks: dict[str, Any] | None = None) -> None:
        self.settings = settings
        self._static_jwks = jwks
        self._cached_jwks: dict[str, Any] | None = jwks
        self._cached_at = monotonic() if jwks is not None else 0.0
        self._lock = threading.Lock()

    def _load_jwks(self, *, force: bool = False) -> dict[str, Any]:
        if self._static_jwks is not None:
            return self._static_jwks
        with self._lock:
            age = monotonic() - self._cached_at
            if not force and self._cached_jwks is not None and age < self.settings.jwks_cache_seconds:
                return self._cached_jwks
            try:
                response = httpx.get(
                    self.settings.identity_jwks_url,
                    timeout=self.settings.default_timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise GatewayError(503, "gateway.identity_unavailable", "Identity public keys are unavailable") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
                raise GatewayError(503, "gateway.identity_invalid_jwks", "Identity public key response is invalid")
            self._cached_jwks = payload
            self._cached_at = monotonic()
            return payload

    def _key_for_kid(self, kid: str):
        attempts = (False,) if self._static_jwks is not None else (False, True)
        for force in attempts:
            for item in self._load_jwks(force=force).get("keys", []):
                if item.get("kid") != kid:
                    continue
                try:
                    return jwt.PyJWK.from_dict(item).key
                except (InvalidTokenError, ValueError, KeyError) as exc:
                    raise GatewayError(401, "gateway.invalid_token", "Identity access token is invalid") from exc
        raise GatewayError(401, "gateway.invalid_token", "Identity access token is invalid")

    def verify(self, token: str) -> IdentityPrincipal:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not isinstance(kid, str) or not kid:
                raise GatewayError(401, "gateway.invalid_token", "Identity access token is invalid")
            claims = jwt.decode(
                token,
                self._key_for_kid(kid),
                algorithms=["EdDSA"],
                issuer=self.settings.identity_issuer,
                audience=self.settings.identity_audience,
                options={"require": ["iss", "aud", "type", "sub", "role", "iat", "exp", "jti"]},
            )
        except GatewayError:
            raise
        except ExpiredSignatureError as exc:
            raise GatewayError(401, "gateway.token_expired", "Identity access token has expired") from exc
        except (InvalidTokenError, ValueError, TypeError) as exc:
            raise GatewayError(401, "gateway.invalid_token", "Identity access token is invalid") from exc

        if claims.get("type") != "access":
            raise GatewayError(401, "gateway.invalid_token", "Identity access token is invalid")
        user_id = claims.get("sub")
        role = claims.get("role")
        if not isinstance(user_id, str) or not user_id or not isinstance(role, str) or not role:
            raise GatewayError(401, "gateway.invalid_token", "Identity access token is invalid")
        return IdentityPrincipal(user_id=user_id, role=role, bearer_token=token)


def extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise GatewayError(401, "gateway.authentication_required", "Authentication is required")
    scheme, separator, value = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not value.strip():
        raise GatewayError(401, "gateway.authentication_required", "Authentication is required")
    return value.strip()
