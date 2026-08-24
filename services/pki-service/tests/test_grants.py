from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import Settings
from app.errors import GuardianError
from app.grants import EnrollmentGrantVerifier


def _verifier(jwks):
    return EnrollmentGrantVerifier(
        Settings(
            database_url="sqlite+pysqlite:///:memory:",
            enrollment_issuer="urn:it-guardian:enrollment",
            enrollment_audience="it-guardian-pki",
            grant_max_lifetime_seconds=120,
        ),
        jwks=jwks,
    )


def test_valid_grant_returns_bound_identity(enrollment_crypto, make_grant):
    _, _, jwks = enrollment_crypto
    token = make_grant(
        claims={
            "tenant_id": "tenant-42",
            "asset_id": "asset-9",
            "device_id": "device-7",
            "sub": "device-7",
            "issuance_id": "11111111-1111-1111-1111-111111111111",
            "csr_sha256": "f" * 64,
        }
    )

    grant = _verifier(jwks).verify(token, expected_type="certificate_issue")

    assert grant.tenant_id == "tenant-42"
    assert grant.asset_id == "asset-9"
    assert grant.device_id == "device-7"
    assert grant.issuance_id == "11111111-1111-1111-1111-111111111111"
    assert grant.csr_sha256 == "f" * 64
    assert grant.token_type == "certificate_issue"


def test_expired_grant_is_rejected(enrollment_crypto, make_grant):
    _, _, jwks = enrollment_crypto
    now = datetime.now(UTC)
    token = make_grant(
        claims={
            "iat": int((now - timedelta(seconds=90)).timestamp()),
            "exp": int((now - timedelta(seconds=1)).timestamp()),
        }
    )
    with pytest.raises(GuardianError) as raised:
        _verifier(jwks).verify(token, expected_type="certificate_issue")
    assert raised.value.code == "pki.grant_expired"


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "urn:wrong:issuer"},
        {"aud": "wrong-audience"},
        {"type": "certificate_rotate"},
        {"sub": "different-device"},
    ],
)
def test_invalid_claim_binding_is_rejected(enrollment_crypto, make_grant, claims):
    _, _, jwks = enrollment_crypto
    token = make_grant(claims=claims)
    with pytest.raises(GuardianError) as raised:
        _verifier(jwks).verify(token, expected_type="certificate_issue")
    assert raised.value.code == "pki.invalid_grant"


def test_grant_longer_than_max_lifetime_is_rejected(enrollment_crypto, make_grant):
    _, _, jwks = enrollment_crypto
    now = datetime.now(UTC)
    token = make_grant(
        claims={
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=121)).timestamp()),
        }
    )
    with pytest.raises(GuardianError) as raised:
        _verifier(jwks).verify(token, expected_type="certificate_issue")
    assert raised.value.code == "pki.invalid_grant"


def test_unknown_kid_and_missing_kid_are_rejected(enrollment_crypto, make_grant):
    private_key, _, jwks = enrollment_crypto
    unknown = make_grant(kid="unknown-key")
    with pytest.raises(GuardianError) as raised:
        _verifier(jwks).verify(unknown, expected_type="certificate_issue")
    assert raised.value.code == "pki.invalid_grant"

    now = datetime.now(UTC)
    claims = {
        "iss": "urn:it-guardian:enrollment",
        "aud": "it-guardian-pki",
        "type": "certificate_issue",
        "sub": "device-1",
        "tenant_id": "tenant-1",
        "asset_id": "asset-1",
        "device_id": "device-1",
        "issuance_id": "11111111-1111-1111-1111-111111111111",
        "csr_sha256": "a" * 64,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=60)).timestamp()),
        "jti": "jti-1",
    }
    without_kid = jwt.encode(claims, private_key, algorithm="EdDSA", headers={"typ": "JWT"})
    with pytest.raises(GuardianError) as raised:
        _verifier(jwks).verify(without_kid, expected_type="certificate_issue")
    assert raised.value.code == "pki.invalid_grant"
