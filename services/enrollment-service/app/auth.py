from __future__ import annotations

import threading
from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable

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
    bearer_token: str


@dataclass(frozen=True)
class TenantAccessDecision:
    allowed: bool
    role: str | None
    tenant_status: str


TenantResolver = Callable[[str, str, str], TenantAccessDecision]


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
                response = httpx.get(self.settings.identity_jwks_url, timeout=5.0)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise GuardianError(503, "enrollment.identity_unavailable", "Identity public keys are unavailable") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
                raise GuardianError(503, "enrollment.identity_invalid_jwks", "Identity public key response is invalid")
            self._cached_jwks = payload
            self._cached_at = monotonic()
            return payload

    def _key_for_kid(self, kid: str):
        attempts = (False,) if self._static_jwks is not None else (False, True)
        for force in attempts:
            for item in self._load_jwks(force=force).get("keys", []):
                if item.get("kid") == kid:
                    try:
                        return jwt.PyJWK.from_dict(item).key
                    except (InvalidTokenError, ValueError, KeyError) as exc:
                        raise GuardianError(401, "enrollment.invalid_token", "Identity access token is invalid") from exc
        raise GuardianError(401, "enrollment.invalid_token", "Identity access token is invalid")

    def verify(self, token: str) -> IdentityPrincipal:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not isinstance(kid, str) or not kid:
                raise GuardianError(401, "enrollment.invalid_token", "Identity access token is invalid")
            claims = jwt.decode(
                token,
                self._key_for_kid(kid),
                algorithms=["EdDSA"],
                issuer=self.settings.identity_issuer,
                audience=self.settings.identity_audience,
                options={"require": ["iss", "aud", "type", "sub", "role", "iat", "exp", "jti"]},
            )
        except GuardianError:
            raise
        except ExpiredSignatureError as exc:
            raise GuardianError(401, "enrollment.token_expired", "Identity access token has expired") from exc
        except (InvalidTokenError, ValueError, TypeError) as exc:
            raise GuardianError(401, "enrollment.invalid_token", "Identity access token is invalid") from exc

        if claims.get("type") != "access":
            raise GuardianError(401, "enrollment.invalid_token", "Identity access token is invalid")
        user_id = str(claims.get("sub", ""))
        role = str(claims.get("role", ""))
        if not user_id or not role:
            raise GuardianError(401, "enrollment.invalid_token", "Identity access token is invalid")
        return IdentityPrincipal(user_id=user_id, role=role, bearer_token=token)


def enforce_enrollment_admin(
    principal: IdentityPrincipal,
    tenant_id: str,
    resolver: TenantResolver,
) -> TenantAccessDecision:
    if principal.role == "platform_admin":
        return TenantAccessDecision(allowed=True, role="platform_admin", tenant_status="active")

    decision = resolver(tenant_id, principal.user_id, principal.bearer_token)
    if not decision.allowed:
        raise GuardianError(403, "enrollment.access_denied", "You do not have access to this tenant")
    if decision.tenant_status != "active":
        raise GuardianError(403, "enrollment.tenant_suspended", "Tenant is suspended")
    if decision.role != "org_admin":
        raise GuardianError(403, "enrollment.org_admin_required", "Organization administrator role is required")
    return decision


def current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> IdentityPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise GuardianError(401, "enrollment.authentication_required", "Authentication is required")
    return request.app.state.identity_verifier.verify(credentials.credentials)
