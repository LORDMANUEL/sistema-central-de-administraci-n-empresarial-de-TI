from __future__ import annotations

import base64
from datetime import UTC, datetime

import httpx
import jwt
import pytest

from app.config import Settings
from app.errors import GuardianError
from app.pki_client import PKIClient
from app.signing import EnrollmentGrantSigner


def _seed() -> str:
    return base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode("ascii")


def _settings() -> Settings:
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        signing_key=_seed(),
        jwt_key_id="enrollment-test-v1",
        jwt_issuer="urn:it-guardian:enrollment",
        pki_audience="it-guardian-pki",
        grant_lifetime_seconds=60,
        pki_service_url="http://pki-service:8000",
        pki_retry_attempts=3,
    )


def _request_body():
    return {
        "issuance_id": "11111111-1111-1111-1111-111111111111",
        "tenant_id": "tenant-1",
        "asset_id": "asset-1",
        "device_id": "device-1",
        "platform": "windows",
        "subject_cn": "WS-SPS-001",
        "csr_pem": "CSR-PUBLIC-MATERIAL",
    }


def _success_body():
    return {
        "certificate_id": "cert-1",
        "issuance_id": "11111111-1111-1111-1111-111111111111",
        "tenant_id": "tenant-1",
        "asset_id": "asset-1",
        "device_id": "device-1",
        "platform": "windows",
        "serial_hex": "01AB",
        "fingerprint_sha256": "f" * 64,
        "subject_cn": "WS-SPS-001",
        "san_uri": "spiffe://guardian/tenant/tenant-1/asset/asset-1/device/device-1",
        "certificate_pem": "CERTIFICATE-PUBLIC-MATERIAL",
        "ca_chain_pem": "CA-CHAIN-PUBLIC-MATERIAL",
        "not_before": "2026-08-24T16:00:00Z",
        "not_after": "2026-09-23T16:00:00Z",
        "status": "active",
        "revoked_at": None,
        "revocation_reason": None,
    }


def _response(status: int, body: dict | None = None) -> httpx.Response:
    request = httpx.Request("POST", "http://pki-service:8000/api/v1/certificates/issue")
    return httpx.Response(status, json=body or {}, request=request)


def test_issue_grant_is_short_lived_bound_and_publicly_verifiable():
    settings = _settings()
    signer = EnrollmentGrantSigner(settings)
    token = signer.create_issue_grant(
        tenant_id="tenant-1",
        asset_id="asset-1",
        device_id="device-1",
        issuance_id="11111111-1111-1111-1111-111111111111",
        csr_sha256="a" * 64,
    )

    jwk = signer.jwks()["keys"][0]
    claims = jwt.decode(
        token,
        jwt.PyJWK.from_dict(jwk).key,
        algorithms=["EdDSA"],
        issuer="urn:it-guardian:enrollment",
        audience="it-guardian-pki",
    )
    header = jwt.get_unverified_header(token)

    assert header["kid"] == "enrollment-test-v1"
    assert claims["type"] == "certificate_issue"
    assert claims["sub"] == "device-1"
    assert claims["tenant_id"] == "tenant-1"
    assert claims["asset_id"] == "asset-1"
    assert claims["device_id"] == "device-1"
    assert claims["issuance_id"] == "11111111-1111-1111-1111-111111111111"
    assert claims["csr_sha256"] == "a" * 64
    assert int(claims["exp"]) - int(claims["iat"]) <= 120
    assert datetime.fromtimestamp(int(claims["exp"]), UTC) > datetime.now(UTC)


@pytest.mark.parametrize("status", [200, 201])
def test_pki_client_accepts_new_or_idempotent_success_without_returning_grant(monkeypatch, status):
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        return _response(status, _success_body())

    monkeypatch.setattr(httpx, "post", fake_post)
    client = PKIClient("http://pki-service:8000", timeout_seconds=4, retry_attempts=3)
    result = client.issue(grant="SERVER-ONLY-GRANT", **_request_body())

    assert result.certificate_id == "cert-1"
    assert result.issuance_id == "11111111-1111-1111-1111-111111111111"
    assert result.certificate_pem == "CERTIFICATE-PUBLIC-MATERIAL"
    assert result.ca_chain_pem == "CA-CHAIN-PUBLIC-MATERIAL"
    assert not hasattr(result, "grant")
    assert calls[0][1] == {"Authorization": "Bearer SERVER-ONLY-GRANT"}
    assert calls[0][2] == _request_body()
    assert calls[0][3] == 4


def test_transient_failures_retry_same_issuance_and_request(monkeypatch):
    calls = []
    outcomes = [
        httpx.ConnectError("uncertain network result"),
        _response(503, {"error": {"code": "pki.database_unavailable"}}),
        _response(200, _success_body()),
    ]

    def fake_post(url, *, headers, json, timeout):
        calls.append((headers.copy(), json.copy()))
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(httpx, "post", fake_post)
    result = PKIClient("http://pki-service:8000", retry_attempts=3).issue(
        grant="SAME-GRANT",
        **_request_body(),
    )

    assert result.certificate_id == "cert-1"
    assert len(calls) == 3
    assert all(call[0]["Authorization"] == "Bearer SAME-GRANT" for call in calls)
    assert all(call[1]["issuance_id"] == "11111111-1111-1111-1111-111111111111" for call in calls)
    assert all(call[1] == _request_body() for call in calls)


def test_exhausted_transient_failures_map_to_pki_unavailable(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: _response(503, {"error": {"code": "pki.ca_unavailable"}}),
    )

    with pytest.raises(GuardianError) as raised:
        PKIClient("http://pki-service:8000", retry_attempts=2).issue(
            grant="GRANT",
            **_request_body(),
        )
    assert raised.value.code == "enrollment.pki_unavailable"


def test_pki_conflict_and_deterministic_rejection_are_not_retried(monkeypatch):
    calls = []

    def conflict(*args, **kwargs):
        calls.append(1)
        return _response(409, {"error": {"code": "pki.issuance_conflict"}})

    monkeypatch.setattr(httpx, "post", conflict)
    with pytest.raises(GuardianError) as raised:
        PKIClient("http://pki-service:8000", retry_attempts=3).issue(
            grant="GRANT",
            **_request_body(),
        )
    assert raised.value.code == "enrollment.pki_issuance_conflict"
    assert len(calls) == 1

    calls.clear()

    def rejected(*args, **kwargs):
        calls.append(1)
        return _response(422, {"error": {"code": "pki.invalid_csr"}})

    monkeypatch.setattr(httpx, "post", rejected)
    with pytest.raises(GuardianError) as raised:
        PKIClient("http://pki-service:8000", retry_attempts=3).issue(
            grant="GRANT",
            **_request_body(),
        )
    assert raised.value.code == "enrollment.pki_rejected"
    assert len(calls) == 1
