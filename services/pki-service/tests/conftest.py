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


def _ed25519_fixture(kid: str):
    private_key = Ed25519PrivateKey.generate()
    raw_public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
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
def enrollment_crypto():
    return _ed25519_fixture("enrollment-test-key")


@pytest.fixture
def make_grant(enrollment_crypto):
    private_key, kid, _ = enrollment_crypto

    def factory(**overrides):
        now = datetime.now(UTC)
        claims = {
            "iss": "urn:it-guardian:enrollment",
            "aud": "it-guardian-pki",
            "type": "certificate_issue",
            "sub": "device-1",
            "tenant_id": "tenant-1",
            "asset_id": "asset-1",
            "device_id": "device-1",
            "issuance_id": str(uuid4()),
            "csr_sha256": "a" * 64,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=60)).timestamp()),
            "jti": str(uuid4()),
        }
        claims.update(overrides.pop("claims", {}))
        headers = {"kid": overrides.pop("kid", kid)}
        headers.update(overrides.pop("headers", {}))
        return jwt.encode(claims, private_key, algorithm="EdDSA", headers=headers)

    return factory


@pytest.fixture
def identity_crypto():
    return _ed25519_fixture("identity-test-key")


@pytest.fixture
def make_identity_token(identity_crypto):
    private_key, kid, _ = identity_crypto

    def factory(*, role: str = "platform_admin", user_id: str = "user-1", **claim_overrides):
        now = datetime.now(UTC)
        claims = {
            "iss": "urn:it-guardian:identity",
            "aud": "it-guardian",
            "type": "access",
            "sub": user_id,
            "role": role,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
            "jti": str(uuid4()),
        }
        claims.update(claim_overrides)
        return jwt.encode(claims, private_key, algorithm="EdDSA", headers={"kid": kid})

    return factory
