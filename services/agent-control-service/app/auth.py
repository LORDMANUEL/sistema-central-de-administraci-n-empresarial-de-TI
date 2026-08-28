from dataclasses import dataclass
from time import monotonic

import httpx
import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError

from .errors import GuardianError

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class IdentityPrincipal:
    user_id: str
    role: str
    bearer_token: str


class AccessTokenVerifier:
    def __init__(self, settings):
        self.settings = settings
        self._cached = None
        self._cached_at = 0.0

    def _jwks(self, force: bool = False):
        if not force and self._cached is not None and monotonic() - self._cached_at < 300:
            return self._cached
        try:
            response = httpx.get(self.settings.identity_jwks_url, timeout=5)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise GuardianError(503, "agent_control.identity_unavailable", "Identity public keys are unavailable") from exc
        self._cached = data
        self._cached_at = monotonic()
        return data

    def verify(self, token: str) -> IdentityPrincipal:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
            key = None
            for force in (False, True):
                for item in self._jwks(force).get("keys", []):
                    if item.get("kid") == kid:
                        key = jwt.PyJWK.from_dict(item).key
                        break
                if key is not None:
                    break
            if key is None:
                raise GuardianError(401, "agent_control.unknown_signing_key", "Unknown Identity signing key")
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
            raise GuardianError(401, "agent_control.token_expired", "Access token has expired") from exc
        except (InvalidTokenError, ValueError) as exc:
            raise GuardianError(401, "agent_control.invalid_token", "Invalid access token") from exc
        if claims.get("type") != "access":
            raise GuardianError(401, "agent_control.invalid_token_type", "Access token required")
        return IdentityPrincipal(str(claims["sub"]), str(claims["role"]), token)


def current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> IdentityPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise GuardianError(401, "agent_control.authentication_required", "Authentication required")
    return request.app.state.auth.verify(credentials.credentials)
