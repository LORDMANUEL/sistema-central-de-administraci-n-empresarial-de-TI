from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI


def _decode_seed(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    raw = base64.urlsafe_b64decode(value + padding)
    if len(raw) != 32:
        raise RuntimeError("PKI_SMOKE_ENROLLMENT_SEED must decode to 32 bytes")
    return raw


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


seed = _decode_seed(os.environ["PKI_SMOKE_ENROLLMENT_SEED"])
private_key = Ed25519PrivateKey.from_private_bytes(seed)
raw_public = private_key.public_key().public_bytes(
    serialization.Encoding.Raw,
    serialization.PublicFormat.Raw,
)

app = FastAPI(title="PKI Smoke Enrollment JWKS Fixture")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/.well-known/jwks.json")
def jwks() -> dict:
    return {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": _b64url(raw_public),
                "use": "sig",
                "alg": "EdDSA",
                "kid": "pki-smoke-enrollment-v1",
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
