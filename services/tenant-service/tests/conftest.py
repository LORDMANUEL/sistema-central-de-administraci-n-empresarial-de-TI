import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

SEED_B64 = "aXQtZ3VhcmRpYW4tZGV2LWVkMjU1MTktc2VlZC12MSE"
KID = "identity-ed25519-v1"
ISSUER = "urn:it-guardian:identity"
AUDIENCE = "it-guardian-services"


def _decode_seed(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@pytest.fixture(scope="session")
def identity_crypto():
    private_key = Ed25519PrivateKey.from_private_bytes(_decode_seed(SEED_B64))
    public_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    jwks = {
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

    def make_token(
        *,
        role: str = "platform_admin",
        user_id: str | None = None,
        token_type: str = "access",
        expires_delta: timedelta = timedelta(minutes=15),
        key=private_key,
        kid: str = KID,
    ) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "sub": user_id or str(uuid4()),
                "role": role,
                "type": token_type,
                "iss": ISSUER,
                "aud": AUDIENCE,
                "iat": now,
                "exp": now + expires_delta,
                "jti": str(uuid4()),
            },
            key,
            algorithm="EdDSA",
            headers={"kid": kid, "typ": "JWT"},
        )

    return jwks, make_token


@pytest.fixture
def auth_header(identity_crypto):
    _, make_token = identity_crypto

    def build(*, role="platform_admin", user_id=None, token_type="access"):
        token = make_token(role=role, user_id=user_id, token_type=token_type)
        return {"Authorization": f"Bearer {token}"}

    return build
