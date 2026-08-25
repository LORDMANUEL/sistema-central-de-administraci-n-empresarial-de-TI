from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@pytest.fixture
def identity_crypto():
    private_key = Ed25519PrivateKey.generate()
    raw_public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    kid = "identity-audit-test-key"
    jwks = {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": _b64url(raw_public),
                "use": "sig",
                "alg": "EdDSA",
                "kid": kid,
            }
        ]
    }
    return private_key, kid, jwks


@pytest.fixture
def make_identity_token(identity_crypto):
    private_key, kid, _ = identity_crypto

    def factory(*, role: str = "platform_admin", user_id: str = "user-1", **overrides):
        now = datetime.now(UTC)
        claims = {
            "iss": "urn:it-guardian:identity",
            "aud": "it-guardian-services",
            "type": "access",
            "sub": user_id,
            "role": role,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
            "jti": str(uuid4()),
        }
        claims.update(overrides)
        return jwt.encode(claims, private_key, algorithm="EdDSA", headers={"kid": kid})

    return factory
