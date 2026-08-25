from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .config import Settings
from .errors import GuardianError


def _decode_seed(value: str) -> bytes:
    if not value:
        raise GuardianError(503, "enrollment.signer_unavailable", "Enrollment signing material is unavailable")
    try:
        padding = "=" * ((4 - len(value) % 4) % 4)
        raw = base64.urlsafe_b64decode(value + padding)
    except Exception as exc:
        raise GuardianError(503, "enrollment.signer_unavailable", "Enrollment signing material is unavailable") from exc
    if len(raw) != 32:
        raise GuardianError(503, "enrollment.signer_unavailable", "Enrollment signing material is unavailable")
    return raw


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class EnrollmentGrantSigner:
    algorithm = "EdDSA"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.private_key = Ed25519PrivateKey.from_private_bytes(_decode_seed(settings.signing_key))
        self.public_key = self.private_key.public_key()

    def jwks(self) -> dict[str, list[dict[str, str]]]:
        public = self.public_key.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        return {
            "keys": [
                {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "x": _b64url(public),
                    "use": "sig",
                    "alg": self.algorithm,
                    "kid": self.settings.jwt_key_id,
                }
            ]
        }

    def create_issue_grant(
        self,
        *,
        tenant_id: str,
        asset_id: str,
        device_id: str,
        issuance_id: str,
        csr_sha256: str,
    ) -> str:
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=self.settings.grant_lifetime_seconds)
        payload = {
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.pki_audience,
            "type": "certificate_issue",
            "sub": device_id,
            "tenant_id": tenant_id,
            "asset_id": asset_id,
            "device_id": device_id,
            "issuance_id": issuance_id,
            "csr_sha256": csr_sha256,
            "iat": now,
            "exp": expires,
            "jti": str(uuid4()),
        }
        return jwt.encode(
            payload,
            self.private_key,
            algorithm=self.algorithm,
            headers={"kid": self.settings.jwt_key_id, "typ": "JWT"},
        )
