from __future__ import annotations

import threading
from dataclasses import dataclass
from time import monotonic
from typing import Any

import httpx
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from .config import Settings
from .errors import GuardianError


@dataclass(frozen=True)
class EnrollmentGrant:
    token_type: str
    subject: str
    tenant_id: str
    asset_id: str
    device_id: str
    issuance_id: str
    csr_sha256: str
    jti: str
    issued_at: int
    expires_at: int


class EnrollmentGrantVerifier:
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
                response = httpx.get(self.settings.enrollment_jwks_url, timeout=5.0)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise GuardianError(
                    503,
                    "pki.enrollment_keys_unavailable",
                    "Enrollment public keys are unavailable",
                ) from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("keys"), list):
                raise GuardianError(
                    503,
                    "pki.enrollment_keys_invalid",
                    "Enrollment public key response is invalid",
                )
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
                        raise GuardianError(401, "pki.invalid_grant", "Enrollment grant is invalid") from exc
        raise GuardianError(401, "pki.invalid_grant", "Enrollment grant is invalid")

    def verify(self, token: str, *, expected_type: str) -> EnrollmentGrant:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            if not isinstance(kid, str) or not kid:
                raise GuardianError(401, "pki.invalid_grant", "Enrollment grant is invalid")
            key = self._key_for_kid(kid)
            claims = jwt.decode(
                token,
                key,
                algorithms=["EdDSA"],
                issuer=self.settings.enrollment_issuer,
                audience=self.settings.enrollment_audience,
                options={
                    "require": [
                        "iss",
                        "aud",
                        "type",
                        "sub",
                        "tenant_id",
                        "asset_id",
                        "device_id",
                        "issuance_id",
                        "csr_sha256",
                        "iat",
                        "exp",
                        "jti",
                    ]
                },
            )
        except GuardianError:
            raise
        except ExpiredSignatureError as exc:
            raise GuardianError(401, "pki.grant_expired", "Enrollment grant has expired") from exc
        except (InvalidTokenError, ValueError, TypeError) as exc:
            raise GuardianError(401, "pki.invalid_grant", "Enrollment grant is invalid") from exc

        try:
            token_type = str(claims["type"])
            subject = str(claims["sub"])
            tenant_id = str(claims["tenant_id"])
            asset_id = str(claims["asset_id"])
            device_id = str(claims["device_id"])
            issuance_id = str(claims["issuance_id"])
            csr_sha256 = str(claims["csr_sha256"])
            jti = str(claims["jti"])
            issued_at = int(claims["iat"])
            expires_at = int(claims["exp"])
        except (KeyError, TypeError, ValueError) as exc:
            raise GuardianError(401, "pki.invalid_grant", "Enrollment grant is invalid") from exc

        if token_type != expected_type or subject != device_id:
            raise GuardianError(401, "pki.invalid_grant", "Enrollment grant is invalid")
        if not all((tenant_id, asset_id, device_id, issuance_id, csr_sha256, jti)):
            raise GuardianError(401, "pki.invalid_grant", "Enrollment grant is invalid")
        if len(csr_sha256) != 64:
            raise GuardianError(401, "pki.invalid_grant", "Enrollment grant is invalid")
        lifetime = expires_at - issued_at
        if lifetime <= 0 or lifetime > self.settings.grant_max_lifetime_seconds:
            raise GuardianError(401, "pki.invalid_grant", "Enrollment grant is invalid")

        return EnrollmentGrant(
            token_type=token_type,
            subject=subject,
            tenant_id=tenant_id,
            asset_id=asset_id,
            device_id=device_id,
            issuance_id=issuance_id,
            csr_sha256=csr_sha256,
            jti=jti,
            issued_at=issued_at,
            expires_at=expires_at,
        )
