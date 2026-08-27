from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.auth import IdentityAccessVerifier
from app.config import Settings
from app.errors import GatewayError


ISSUER = "urn:it-guardian:identity"
AUDIENCE = "it-guardian-services"
KID = "identity-test-ed25519"


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _jwks(private_key: Ed25519PrivateKey) -> dict:
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    return {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": _b64url(public_raw),
                "use": "sig",
                "alg": "EdDSA",
                "kid": KID,
            }
        ]
    }


def _token(
    private_key: Ed25519PrivateKey,
    *,
    token_type: str = "access",
    role: str = "platform_admin",
    expires_delta: timedelta = timedelta(minutes=5),
    kid: str = KID,
) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "type": token_type,
            "sub": str(uuid4()),
            "role": role,
            "iat": int(now.timestamp()),
            "exp": int((now + expires_delta).timestamp()),
            "jti": str(uuid4()),
        },
        private_key,
        algorithm="EdDSA",
        headers={"kid": kid},
    )


def _settings() -> Settings:
    return Settings(identity_issuer=ISSUER, identity_audience=AUDIENCE)


def test_valid_identity_access_token_is_verified_from_ed25519_jwks():
    private_key = Ed25519PrivateKey.generate()
    token = _token(private_key, role="security_admin")
    verifier = IdentityAccessVerifier(_settings(), jwks=_jwks(private_key))

    principal = verifier.verify(token)

    assert principal.user_id
    assert principal.role == "security_admin"
    assert principal.bearer_token == token


def test_expired_access_token_is_rejected_with_stable_code():
    private_key = Ed25519PrivateKey.generate()
    token = _token(private_key, expires_delta=timedelta(seconds=-5))
    verifier = IdentityAccessVerifier(_settings(), jwks=_jwks(private_key))

    with pytest.raises(GatewayError) as raised:
        verifier.verify(token)

    assert raised.value.status_code == 401
    assert raised.value.code == "gateway.token_expired"


def test_wrong_signature_unknown_kid_and_refresh_token_are_rejected():
    trusted = Ed25519PrivateKey.generate()
    untrusted = Ed25519PrivateKey.generate()
    verifier = IdentityAccessVerifier(_settings(), jwks=_jwks(trusted))

    for token in (
        _token(untrusted),
        _token(trusted, kid="unknown-key"),
        _token(trusted, token_type="refresh"),
    ):
        with pytest.raises(GatewayError) as raised:
            verifier.verify(token)
        assert raised.value.status_code == 401
        assert raised.value.code == "gateway.invalid_token"


def test_verifier_requires_role_and_access_claim_structure():
    private_key = Ed25519PrivateKey.generate()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "type": "access",
            "sub": str(uuid4()),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "jti": str(uuid4()),
        },
        private_key,
        algorithm="EdDSA",
        headers={"kid": KID},
    )
    verifier = IdentityAccessVerifier(_settings(), jwks=_jwks(private_key))

    with pytest.raises(GatewayError) as raised:
        verifier.verify(token)

    assert raised.value.code == "gateway.invalid_token"
